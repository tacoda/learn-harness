# 12 · Callbacks & Runtime

## Mental model

Callbacks are the **event system** underneath every Runnable: as a run executes, it fires lifecycle events (model start/end, tool start/end, chain step, token, error) to any handlers you've attached. You rarely wire them by hand — you *configure* them through `RunnableConfig`, the sideband dict that carries callbacks, tags, metadata, and a run id through the entire execution tree. This is the machinery that powers LangSmith tracing: turn on tracing and a callback handler is attached for you, emitting every event to the trace. Understanding config and callbacks is understanding *how observability threads through a run without you passing it around*.

## In depth

### RunnableConfig

Every `.invoke` / `.stream` accepts a `config`. It propagates automatically to every nested Runnable — set it once at the top, it reaches the deepest tool:

```python
from langchain_core.runnables import RunnableConfig

config: RunnableConfig = {
    "run_name": "answer_question",        # human-readable name in traces
    "tags": ["prod", "rag", "v2"],        # filterable labels
    "metadata": {"user_id": "u_42",       # structured, queryable attributes
                 "tenant": "acme"},
    "callbacks": [...],                    # handlers (usually auto-attached)
    "max_concurrency": 4,                  # cap parallel branches
    "configurable": {"thread_id": "t1"},   # runtime overrides (e.g. memory)
}
result = agent.invoke(inputs, config=config)
```

Because config propagates, tags and metadata set here appear on **every** step in the trace — the model call, each tool call, each nested chain — without threading arguments through your code. This is the single most useful thing to internalize: **tag once, filter everywhere.**

### Tags, metadata, run_name, run_id

- **`tags`** — flat labels for filtering runs in LangSmith ("prod", experiment ids). Cheap, high-value.
- **`metadata`** — structured key/values for querying and grouping (user id, tenant, prompt version). This is how you slice traces by cohort.
- **`run_name`** — names the run so it's legible in the trace tree instead of a class name.
- **`run_id`** — a UUID identifying the run; capture it to correlate a trace with your own logs, or to attach feedback later. You can supply one, or read the generated one.

### Callback handlers

A handler implements the lifecycle methods it cares about. This is the raw layer LangSmith builds on, and what you subclass for custom, in-process observability:

```python
from langchain_core.callbacks import BaseCallbackHandler

class TimingHandler(BaseCallbackHandler):
    def on_chat_model_start(self, serialized, messages, **kwargs):
        self._t0 = time.perf_counter()
    def on_llm_end(self, response, **kwargs):
        print(f"model took {time.perf_counter() - self._t0:.2f}s")
    def on_tool_start(self, serialized, input_str, **kwargs):
        print(f"tool start: {serialized.get('name')}({input_str})")
    def on_tool_error(self, error, **kwargs):
        print(f"tool error: {error}")

agent.invoke(inputs, config={"callbacks": [TimingHandler()]})
```

Common hooks: `on_chat_model_start`, `on_llm_new_token`, `on_llm_end`, `on_tool_start` / `on_tool_end` / `on_tool_error`, `on_chain_start` / `on_chain_end`, `on_retriever_end`. Implement only what you need; unimplemented events are ignored. Handlers passed in config propagate to child runs just like tags — one handler observes the whole tree.

### Callbacks vs. middleware vs. astream_events

Three overlapping ways to observe/intercept — pick by intent:

| | Purpose | Can modify the run? |
|---|---|---|
| **Callbacks** | Passive observation / side-effect logging | No — observe only |
| **Middleware** (module 10) | Intercept and *change* the agent loop | Yes — rewrite state, retry, gate |
| **`astream_events`** (module 11) | Consume events as a stream in your own code | No — observe only |

Callbacks fire side effects (log, time, count) as the run proceeds; `astream_events` surfaces the same lifecycle as an async stream you iterate; middleware is the only one that alters behavior. Reach for callbacks when you want to *watch* without touching control flow.

### How this powers LangSmith

LangSmith tracing is a callback handler, activated by environment variables — no code change:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=learn-harness
```

With those set, a tracing handler is auto-attached to every run, emitting the full callback stream to LangSmith. Your `tags`, `metadata`, `run_name`, and `run_id` from config all land on the trace — which is why disciplined config hygiene (tagging by environment, stamping user/tenant metadata) pays off directly as filterable, queryable traces. This is the request-time half of the observability story; the LangSmith track covers the analysis half (datasets, evaluators, experiments).

## Why it matters

Callbacks-via-config is the design that decouples **observability from business logic**. You never sprinkle logging calls through your chain; you attach handlers (or just turn on tracing) at the edge, and the event system carries them everywhere via config propagation. That's what makes it possible to trace an arbitrarily deep agent — every model call, tool call, and retrieval — with zero instrumentation inside the components themselves. The discipline it demands is config hygiene: tags and metadata are only as useful as they are consistent, and a run untagged at the top is a run you can't find later. The tradeoff for the automatic propagation is a little indirection — behavior configured at the edge affects the whole tree — but that's exactly the property that makes it scale.

## Pitfalls

- **No tags or metadata.** Untagged runs are unfindable in a busy project. Tag by environment and stamp user/tenant metadata from day one.
- **Expecting callbacks to change behavior.** They're observe-only. To alter the loop (retry, gate, rewrite), use middleware.
- **Re-passing callbacks into nested calls.** Config propagates automatically. Manually threading callbacks into child Runnables double-fires events.
- **Heavy work in a handler.** Callbacks run in the request path (sync handlers block it). Keep them light or offload; a slow `on_llm_end` slows every call.
- **Losing the `run_id`.** Without capturing it you can't correlate a trace with your own logs or attach feedback. Capture it when you need cross-system correlation.
- **Assuming tracing needs code.** It doesn't — `LANGSMITH_TRACING=true` plus a key is the whole setup. Adding manual trace calls on top usually duplicates spans.
- **Stale callback signatures.** Handler method signatures live in `langchain_core.callbacks`; old tutorials sometimes import from moved paths. Subclass `BaseCallbackHandler` from core.

## Exercises

1. Invoke an agent with `tags` and `metadata` in the config; turn on LangSmith tracing and confirm they appear on every step.
2. Write a `BaseCallbackHandler` that times each model call and counts tool calls; attach it via config.
3. Add `on_tool_error` to that handler, force a tool to raise, and observe the error event fire.
4. Capture the `run_id` from a run and log it alongside your own application log line for correlation.
5. Compare observing one run with a callback handler vs. `astream_events` — note which lets you *react mid-run* and which is post-hoc.

## Further reading

- Callbacks: https://docs.langchain.com/oss/python/langchain/callbacks
- RunnableConfig: https://docs.langchain.com/oss/python/langchain/runnables
- LangSmith tracing: https://docs.langchain.com/langsmith/observability-quickstart
- Streaming (`astream_events`): https://docs.langchain.com/oss/python/langchain/streaming
