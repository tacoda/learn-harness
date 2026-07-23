# 01 · Tracing & Observability

## Mental model

LangSmith's observability plane is built on two nested nouns:

- A **run** is a single logged unit of work — one LLM call, one tool invocation, one function execution. Every run has a `run_type` (`llm`, `tool`, `chain`, `retriever`, `prompt`, `parser`), inputs, outputs, timing, and optionally an error.
- A **trace** is a whole tree of runs that share a root. When your `assistant()` function calls `get_context()` and then the model, those become child runs nested under the assistant's root run. The trace *is* the run tree.

```
trace (root run: assistant)
├── run: get_context      (run_type="tool")
└── run: chat.completions (run_type="llm")
```

Traces land in a **project** — a named bucket (`LANGSMITH_PROJECT`). Think of a project as the equivalent of a logging stream: one per app, or one per environment (`my-app-dev`, `my-app-prod`). If you set nothing, traces go to a project literally named `default`.

The key mental shift from ordinary logging: you are not emitting flat lines, you are emitting a *shape*. The value comes from being able to walk the tree — expand the LLM call that failed, see the exact prompt it received after three layers of context assembly, read the token counts and latency at every node.

## In depth

### Turning tracing on

Tracing is controlled entirely by environment variables. No code change is required to start or stop it:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...
export LANGSMITH_PROJECT=my-app          # optional; defaults to "default"
export LANGSMITH_WORKSPACE_ID=...         # only if your key spans multiple workspaces
```

`LANGSMITH_TRACING=true` is the master switch. It gates the `@traceable` decorator and the `trace` context manager. Flip it to `false` (or unset it) and the same code runs with tracing disabled — this is why you keep the toggle in the environment rather than in code.

### Auto-tracing LangChain and LangGraph

This is the payoff of the layered stack from the foundations track. If you build with LangChain or LangGraph, **you get tracing for free**. Set the environment variables and every model call, tool call, retriever, and graph node emits a run automatically — no decorators, no wrappers, no instrumentation in your business logic. A `create_agent` invocation produces a full trace tree: the agent node, each tool call, each model call, all nested correctly.

That is the intended default. You only reach for manual instrumentation (covered in file 09) when you are tracing code that does *not* go through LangChain — a raw provider SDK call, a bare Python function, a custom retrieval step.

### Reading a trace

In the UI, a trace opens as a tree in the left rail with a detail pane on the right. For any selected run you see:

- **Inputs and outputs** — the exact payloads, rendered as chat messages for LLM runs.
- **Latency** — wall-clock time for that node and its subtree.
- **Tokens and cost** — for LLM runs, input/output token counts and a derived dollar cost.
- **Metadata and tags** — anything you attached (see below).
- **Errors** — stack traces and error messages on failed runs, which surface in red.

The discipline to build: when something goes wrong, do not re-read your code first. Open the trace, find the run that failed or produced the wrong output, and read the *actual* inputs it received. Most agent bugs are context bugs — the model got something you did not expect — and the trace shows you exactly that.

### Tags and metadata

Tags are free-form string labels; metadata is arbitrary key/value data. Both are for later filtering and both can be set statically or dynamically:

```python
import langsmith as ls

@ls.traceable(tags=["checkout-flow"], metadata={"version": "v2"})
def handle(request):
    rt = ls.get_current_run_tree()      # grab the current run
    rt.metadata["user_id"] = request.user_id   # set dynamically
    rt.tags.append("premium")
    ...
```

You can also inject at call time via `langsmith_extra={"tags": [...], "metadata": {...}}`, or set defaults for a whole scope with `ls.tracing_context(metadata={...})`. LangChain and LangGraph accept `tags` and `metadata` in their `config` argument, which flows to the emitted runs.

Attach the things you will want to slice by later: user or tenant id, app version, feature flag, request source. LangSmith also stamps its own `ls_*` metadata automatically (`ls_provider`, `ls_model_name`, `ls_run_depth`, `ls_temperature`).

### Filtering runs

In the UI, projects have a filter bar; programmatically you use `client.list_runs` with a filter string:

```python
from langsmith import Client
client = Client()

runs = client.list_runs(
    project_name="my-app",
    filter='and(eq(metadata_key, "user_id"), eq(metadata_value, "u_123"))',
)

# Root runs only (top-level traces, not children):
runs = client.list_runs(
    project_name="my-app",
    filter='eq(metadata_key, "ls_run_depth") and eq(metadata_value, 0)',
)
```

Filtering on `ls_run_depth = 0` to get just root runs is a common idiom — it turns a soup of every nested run into the list of actual top-level requests.

## Why it matters

Without tracing you debug agents by re-reading code and guessing what the model saw. That does not scale past a trivial prompt. An agent's behavior is a function of the exact context it received on each step, and that context is assembled by layers of your code plus the framework. The trace is the only place the *assembled* context is visible. Wire it in on day one, before you have bugs, because the trace you did not capture is the one you needed.

Tracing is also the substrate for everything else in this track: datasets are built from traces, experiments are traces grouped and scored, monitoring aggregates over traces, and feedback attaches to runs. If you skip observability you cannot do evaluation either.

## Pitfalls

- **Forgetting `LANGSMITH_TRACING=true`.** The other variables are inert without it. A common failure is setting the API key, seeing no traces, and concluding LangSmith is broken.
- **Everything landing in `default`.** If you never set `LANGSMITH_PROJECT`, dev noise, tests, and production all pile into one project and become impossible to reason about. Set a distinct project per environment.
- **Not attaching identifiers.** Traces without a user id, tenant, or version are hard to filter when you have thousands. Attach metadata proactively — you cannot backfill it.
- **Treating tags as metadata.** Tags are for coarse categorical filtering; high-cardinality values (like user ids) belong in metadata, not tags.
- **Leaking secrets into traces.** Inputs and outputs are captured verbatim. If your payloads contain PII or credentials, you need redaction (file 09) — the trace store is not a safe place for raw secrets by default.

## Exercises

1. Set the four tracing environment variables and run any LangChain or `create_agent` example from the earlier tracks. Open the resulting trace in the UI and identify the root run, an LLM child run, and its token counts.
2. Add `metadata={"env": "dev"}` to a traceable function, run it a few times, then use `client.list_runs` with a filter that returns only those runs.
3. Deliberately raise an exception inside a traced tool function. Find the failed run in the UI and confirm the error and the inputs that triggered it are both visible.
4. Explain to a colleague why filtering on `ls_run_depth = 0` gives you "one row per request" and when you would *not* want that filter.

## Further reading

- Observability quickstart: https://docs.langchain.com/langsmith/observability-quickstart
- Tracing concepts: https://docs.langchain.com/langsmith/observability-concepts
- Add metadata and tags: https://docs.langchain.com/langsmith/add-metadata-tags
- Filter traces in the application: https://docs.langchain.com/langsmith/filter-traces-in-application
- Log traces to a project: https://docs.langchain.com/langsmith/log-traces-to-project
