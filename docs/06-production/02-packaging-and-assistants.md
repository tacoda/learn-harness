# 02 · Packaging & Assistants

## Mental model

A compiled graph is a Python object living in a variable. To operate it you need to turn it into a **deployable unit**: a thing with a manifest, declared dependencies, declared secrets, and a stable network contract. Packaging is that translation, and it is deliberately the *same* whether you deploy locally, to a container, or to the cloud.

Three layers, and the pattern is that each is independent of the ones below it:

```
   client  ─── talks to ───▶  Threads & Runs API      ← the deployment contract (never changes)
                                     │ runs
                              Assistants               ← versioned CONFIG of a graph (change without redeploy)
                                     │ configure
                              Graph (code)             ← what you built; declared in langgraph.json
```

- The **graph** is code. It changes only when logic changes, and changing it means a redeploy.
- An **assistant** is a graph plus a specific configuration (prompt, model, tools) and it is *versioned*. Most day-to-day tuning happens here, with no code change and instant rollback.
- The **Threads & Runs API** is the contract your clients depend on. It stays stable while the graph and assistants churn underneath it.

Keeping these three separate is the whole trick. It is why a product manager can tune a prompt without a deploy, why you can A/B two behaviours of one graph, and why rollback is a config pointer flip rather than a git revert. The separation is not `support-triage`-specific — it is how you keep *any* agent changeable in production.

## In depth

### Project layout

A deployable LangGraph app is a normal Python project plus a manifest at the root:

```
support-triage/
├── langgraph.json          # the manifest — the deployable contract
├── pyproject.toml          # dependencies (or requirements.txt)
├── .env                    # local secrets (never committed)
└── src/
    └── support_triage/
        ├── __init__.py
        ├── graph.py        # exports the compiled graph
        └── tools.py        # look_up_order, search_help_center
```

`graph.py` exports a compiled graph — the exact object you have been building all along:

```python
# src/support_triage/graph.py
from langchain.agents import create_agent
from .tools import look_up_order, search_help_center

# create_agent compiles to a LangGraph graph (see docs/00-foundations)
graph = create_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[look_up_order, search_help_center],
    system_prompt="You are a support triage agent. Resolve or escalate.",
)
```

Note there is **no checkpointer passed here**. In a deployment, the Agent Server supplies a production checkpointer (Postgres) for you — passing your own `InMemorySaver` would be both redundant and wrong (file 03). Locally you compile the same object.

### The `langgraph.json` manifest

The manifest is the single source of truth every deployment mode reads. Minimal form:

```json
{
  "dependencies": ["."],
  "graphs": {
    "triage": "./src/support_triage/graph.py:graph"
  },
  "env": ".env"
}
```

The fields you will actually use, grounded in the current CLI reference:

- **`dependencies`** — where the code and its requirements live. `["."]` means "this project" (it reads your `pyproject.toml`/`requirements.txt`). You can also list published packages.
- **`graphs`** — a map of *graph name* → `path:variable`. The value must resolve to a **compiled** graph (or a factory that returns one), not a `StateGraph` builder. The name (`"triage"`) is what clients pass as the graph/assistant identifier over the API. You can expose several graphs from one app.
- **`env`** — a path to a `.env` file *or* an inline mapping of variable → value. For local runs only; production sets env in the deployment environment (see below).
- **`python_version`** / **`node_version`** — pin the runtime.
- **`dockerfile_lines`** — extra Dockerfile lines for system libraries the build needs.
- **`checkpointer`** — configure the persistence backend: `backend` is `"default"` (Postgres), `"mongo"`, or `"custom"`; plus optional `ttl` for checkpoint expiry. You rarely set this; the default is Postgres.
- **`store`** — enable the long-term memory store, optionally with semantic-search `index` (`embed`, `dims`, `fields`) and item `ttl`.
- **`auth`** — path to a `langgraph_sdk.Auth` handler (e.g. `./src/support_triage/auth.py:auth`) that gates who can hit the API.
- **`http`** — HTTP server config: CORS, custom routes, middleware order.
- **`base_image`** / **`image_distro`** — pin the server base image and Linux distro (`debian`, `wolfi`, `bookworm`, `bullseye`) for reproducible builds.

The reusable idea: **the manifest declares everything the runtime needs to stand your graph up.** When your app grows to five graphs and a custom auth handler, it is still one `langgraph.json` — the file scales with the app.

### Dependencies, environment, and secrets

Three distinct things, kept in three distinct places:

- **Dependencies** → your `pyproject.toml`/`requirements.txt`, referenced by `dependencies` in the manifest. The build installs them.
- **Environment / config** → the `env` key locally; the **deployment environment** in production. Never bake config into the image.
- **Secrets** (API keys, DB URLs) → `.env` locally (git-ignored), and the platform's secret store in production. The manifest references the file; the values never enter the repo or the image.

The rule that transfers to any complexity: **secrets are injected at deploy time, never committed and never hardcoded in the graph.** A twelve-agent system has more keys, not a different mechanism.

### The local Agent Server: `langgraph dev`

With the manifest in place, install the CLI and run the local server:

```bash
pip install -U "langgraph-cli[inmem]"
langgraph dev
```

`langgraph dev` starts a lightweight in-memory Agent Server (no Docker required, hot reload) on `http://127.0.0.1:2024`, opens the Studio IDE against it, and serves interactive API docs at `/docs`. State persists to a local directory — good enough to exercise threads, not a production backend. This is your **local** stage from file 01. Useful flags: `--no-browser`, `--port`, `--no-reload`, `--tunnel` (expose via a public URL for a remote frontend).

Wire LangSmith tracing here from the first run (set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in `.env`) so you are never developing blind — see `docs/03-langsmith/01-tracing-and-observability.md`.

### Assistants: versioned configs of a graph

When the server (local or deployed) loads a graph, it **auto-creates a default assistant** using the graph's default configuration. An assistant is "an instance of a graph with a specific configuration." You create more by supplying `context` values that your graph reads at runtime.

The graph declares a context schema; the assistant fills it in:

```python
# graph reads model_name from runtime context
class ContextSchema(TypedDict):
    model_name: str
    system_prompt: str
```

```python
from langgraph_sdk import get_client
client = get_client(url="http://127.0.0.1:2024")

# a "concise" assistant and a "verbose" assistant, same graph, no redeploy
concise = await client.assistants.create(
    graph_id="triage",
    name="Triage — concise",
    context={"model_name": "anthropic:claude-haiku-4-5",
             "system_prompt": "Answer in one short paragraph. Escalate if unsure."},
)
```

Each `create` returns an `assistant_id` (a UUID). Assistants are **versioned**: updating one creates a new version, and you can point the assistant at any version — which is exactly the rollback and canary mechanism of files 03 and 05. This is the separation of *code* (graph) from *configuration* (assistant) made operational.

### Threads & Runs: the deployment contract

The server exposes the runtime you already know as a REST API, and this API is the contract clients code against:

- **Threads** embody a `thread_id`: create one, run graphs against it, and its checkpointed state persists across runs. The API lists threads, reads state/history, and forks state (the time-travel of `docs/02-langgraph/11-durable-execution-and-time-travel.md`, over HTTP).
- **Runs** are an execution of an assistant on a thread. You can pass either a **graph ID** (`"triage"` → uses the default assistant) or a specific **assistant ID** (a UUID → that exact config). Runs can stream, run in the background, or be scheduled (cron).

```python
# stateless run against the default assistant of the "triage" graph
async for chunk in client.runs.stream(
    None,               # no thread → stateless
    "triage",           # graph ID (default assistant) OR an assistant UUID
    input={"messages": [{"role": "human", "content": "Where is order 4471?"}]},
    stream_mode="messages-tuple",
):
    print(chunk.event, chunk.data)
```

The core resources — **assistants, threads, runs, cron jobs** — are always persisted in Postgres by the server (file 03). That the same four API operations back a trivial agent and a multi-agent system is exactly why the contract is stable: complexity lives inside the graph, not in the interface.

## Why it matters

Packaging is the seam between "code that runs on my machine" and "a service my organisation depends on." Getting the seam right buys you the two properties that make production survivable: a **stable contract** (clients depend on Threads/Runs, not on your graph internals, so you can rewrite the graph without breaking them) and **config/code separation** (you tune behaviour via assistant versions, cheaply and reversibly, instead of shipping code for every prompt tweak). Both are declared, not coded — the manifest and the assistant are data, which is what makes them auditable, diffable, and rollback-able. Skip this and every change is a code deploy and every rollback is a git operation under pressure.

## Pitfalls

- **Pointing `graphs` at an uncompiled builder.** The value must resolve to a *compiled* graph or a factory returning one — export the compiled object, not the `StateGraph` builder.
- **Baking a checkpointer into the graph for deployment.** The Agent Server supplies the production Postgres checkpointer. A hardcoded `InMemorySaver` silently loses durability in prod (file 03, `docs/05-expert/06-production-reliability.md`).
- **Committing secrets.** Keep keys in `.env` (git-ignored) locally and in the platform secret store in prod. The manifest references files; it never contains values.
- **Confusing a graph with an assistant.** Graph = code (redeploy to change). Assistant = config + version (change live, roll back instantly). Most tuning is an assistant version, not a code change.
- **Shipping `langgraph dev` to production.** It is in-memory, single-process, no durability. It is the local stage only — production is the deployed Agent Server (file 03).
- **Leaking graph internals into the client contract.** Clients should speak Threads/Runs and assistant IDs, never reach into graph state shapes. Keep the interface at the API boundary so the graph stays free to change.

## Exercises

1. Write a minimal `langgraph.json` for `support-triage` that exports a compiled `graph`, then run `langgraph dev` and invoke it from both Studio and `/docs`. Confirm a trace appears in LangSmith.
2. Using the local server, create a thread, run the graph on it twice, and read the thread's state history over the API. Map each call to the in-process method from `docs/02-langgraph/05-persistence-checkpointers.md`.
3. Create two assistants on the same graph that differ only in `context` (e.g. concise vs verbose). Run each and diff the traces. Explain what changing one requires versus a code change.
4. Add one production concern to the manifest (an `auth` handler, or `store` with semantic search) and describe how the same field would serve a far more complex agent unchanged.

## Further reading

- Application structure & `langgraph.json`: https://docs.langchain.com/langsmith/application-structure
- LangGraph app structure (OSS): https://docs.langchain.com/oss/python/langgraph/application-structure
- LangGraph CLI (`dev`, config fields): https://docs.langchain.com/langsmith/cli
- Run a local server: https://docs.langchain.com/oss/python/langgraph/local-server
- Assistants: https://docs.langchain.com/langsmith/assistants
- Manage assistants (create/version via SDK): https://docs.langchain.com/langsmith/configuration-cloud
- Agent Server (threads, runs, persistence): https://docs.langchain.com/langsmith/agent-server
- Sibling: `docs/02-langgraph/13-deployment-langgraph-platform.md`, `docs/02-langgraph/05-persistence-checkpointers.md`
