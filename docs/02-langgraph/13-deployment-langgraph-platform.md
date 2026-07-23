# 13 · Deployment & the LangGraph Platform

## Mental model

A compiled graph is a Python object. To *serve* it — expose it over HTTP, manage threads and their persisted state, run it with concurrency and durability — you need a server around it. LangGraph provides one, and the same server runs from your laptop to production:

- **`langgraph dev`** — the local development server. Starts an in-memory API server plus a Studio UI for inspecting and driving your graph. For iteration, not production.
- **`langgraph.json`** — the config file that tells the tooling *what* to serve: which graph object, what dependencies, what environment.
- **Agent Server / LangGraph Platform** — the managed, production-grade deployment. It hosts your graphs behind a stable API, backs them with persistent checkpointers and stores, and adds the **Assistants** and **Threads** abstractions for building applications.

The mental model: `langgraph.json` describes your app; `langgraph dev` runs that description locally; the Platform runs the same description at scale. Your graph code doesn't change between them — deployment is configuration, not a rewrite.

## In depth

### `langgraph.json`

At the project root, a small JSON file declares the deployable app:

```json
{
  "dependencies": ["."],
  "graphs": {
    "agent": "./src/agent.py:agent"
  },
  "env": ".env"
}
```

- **`dependencies`** — where to find your code and its requirements (`"."` means this project; you can also list packages).
- **`graphs`** — a map of graph name → `path:variable`. Here, the server serves the `agent` object exported from `src/agent.py` under the name `"agent"`. You can expose several graphs.
- **`env`** — the environment file (API keys, DB URLs).

The value each graph points at is a **compiled graph** (or a factory that returns one). This file is the contract every deployment mode reads.

### Local development: `langgraph dev`

With `langgraph.json` in place, run the dev server:

```bash
langgraph dev
```

It prints the local endpoints — an API at `http://127.0.0.1:2024`, interactive API docs at `/docs`, and a Studio UI (hosted, pointed at your local server). Studio lets you invoke the graph, watch state stream, inspect checkpoints, and step through interrupts visually. This is an *in-memory* server meant for development; it explicitly tells you to use a real deployment for production. It's the fastest way to exercise a graph end-to-end without writing a client.

### Assistants

An **assistant** is a *configured instance* of a graph: the same graph plus a specific configuration (model, prompt, tool settings) and metadata. One graph can back many assistants — e.g. a "concise" and a "verbose" variant of the same agent — and assistants are versioned, so you can update configuration without redeploying code. This separates the *code* (the graph) from the *configuration* (the assistant), which is what lets non-engineers tune behaviour and lets you A/B configurations.

### Threads and the API

The Platform exposes the runtime you already know as a REST API:

- **Threads** — the server-side embodiment of a `thread_id` (chapter 5). You create a thread, then run graphs against it; its checkpointed state persists across runs. The Threads API lets you list threads, read their state and history, and update/fork state (the time-travel of chapter 11, over HTTP).
- **Runs** — an execution of an assistant on a thread. Runs can be streamed (chapter 8's stream modes are exposed over the API), run in the background, or scheduled (cron). The server handles concurrency, retries, and durability.

So a client application does: create/reuse a thread, start a run of an assistant on it, stream the output, and later resume or inspect via the same thread. All the concepts from earlier chapters — persistence, streaming, HITL interrupts, time-travel — surface as API operations.

### Deployment options

The Platform supports a spectrum: a fully-managed cloud SaaS, a "hybrid" mode (managed control plane, your infrastructure for the data plane), and fully self-hosted. The choice is about where your data and compute live and your compliance needs; the graph and `langgraph.json` are identical across them. Production deployments back the server with a persistent checkpointer (Postgres) and store, so threads and long-term memory survive restarts and scale across workers.

## Why it matters

The gap between "my graph runs in a notebook" and "my agent serves users" is entirely infrastructure: an HTTP surface, durable per-user state, concurrency, background/scheduled runs, and a way to tune behaviour without redeploying. Rebuilding that yourself is a lot of undifferentiated work — and easy to get subtly wrong around persistence and resumption. The Platform provides it as the productionization of the exact runtime you've been learning, so your effort stays in the graph. Even if you never use the managed Platform, `langgraph dev` and `langgraph.json` are the fastest path to exercising and debugging a graph as a real service.

## Pitfalls

- **Pointing `graphs` at an uncompiled builder.** The value must resolve to a *compiled* graph (or a factory returning one), not a `StateGraph` builder. Export the compiled object.
- **Shipping the in-memory dev server to production.** `langgraph dev` is explicitly for development — in-memory, single-process. Production needs the Platform/Agent Server with persistent backends.
- **Confusing a graph with an assistant.** The graph is code; the assistant is a graph + configuration + version. Tuning behaviour usually means a new assistant/version, not a code change.
- **Forgetting a production checkpointer/store.** Threads and long-term memory only persist if the deployment is backed by Postgres (or equivalent). An in-memory backend loses state on restart.
- **Hardcoding secrets instead of using `env`.** Put keys and connection strings in the `.env` referenced by `langgraph.json`, not in code.
- **Stale-tutorial trap.** Deployment tooling and product naming have evolved (the platform and its Studio/Server naming changed over time, and hosting is now under LangSmith Deployment). Follow the current docs.langchain.com deployment pages rather than older blog posts, and verify the CLI commands against the installed `langgraph-cli` version.

## Exercises

1. Write a minimal `langgraph.json` for a project that exports a compiled `agent` from `src/agent.py`. Run `langgraph dev` and invoke the graph from the Studio UI and from `/docs`.
2. Using the local server's API, create a thread, run the graph on it twice, and read the thread's state history over HTTP. Map each API call to the equivalent in-process method from earlier chapters.
3. Describe (no code) two assistants backed by the *same* graph that differ only in configuration, and what changing one would require versus a code change.
4. List, for your own use case, which deployment option (cloud / hybrid / self-hosted) fits and why, naming the data-residency or compliance driver.

## Further reading

- Application structure and `langgraph.json`: https://docs.langchain.com/oss/python/langgraph/application-structure
- Local server (`langgraph dev`) and Studio: https://docs.langchain.com/oss/python/langgraph/local-server
- Assistants: https://docs.langchain.com/langsmith/assistants
- Deployment options: https://docs.langchain.com/langsmith/deployment-options
