# 09 · Instrumenting Your Code (@traceable)

## Mental model

File 01 said LangChain and LangGraph auto-trace with zero code changes. This file is the other case: **code that does not go through those libraries**. A raw `openai` call, a bare Python function, a custom retriever, a call to some internal service — none of it emits runs unless you instrument it.

There are three instruments, in ascending order of control:

```
@traceable            ← decorate a function; it becomes a run automatically
wrap_openai(...)      ← wrap a provider client; every call it makes is a run
RunTree / trace()     ← construct and post runs by hand; full manual control
```

The right one is almost always `@traceable` or `wrap_openai`. `RunTree` is the escape hatch for when you need to emit a run for something that is not a Python function call you control the boundary of. All three produce the same nested run tree from file 01 — the choice is about ergonomics, not capability.

The core insight: a trace's structure mirrors your *call stack*. When a `@traceable` function calls another `@traceable` function, the inner one nests under the outer one automatically, because the tracing context propagates through the call. You get the tree for free from ordinary function composition.

## In depth

### `@traceable`

Decorate any function; its inputs (arguments) and output (return value) are captured as a run:

```python
from langsmith import traceable

@traceable                     # defaults: run_type="chain", name=function name
def assistant(question: str) -> str:
    context = get_context(question)   # if also @traceable, nests here
    return answer(context, question)

@traceable(run_type="tool")    # classify this as a tool span
def get_context(question: str) -> str:
    return knowledge_base.search(question)
```

Nesting is automatic: because `get_context` is called inside `assistant`, its run becomes a child of the `assistant` run. You do not wire the tree — you *write* the tree as normal function calls. `@traceable` gates on `LANGSMITH_TRACING=true`; with it unset, the decorator is a no-op and your functions run normally.

Useful decorator arguments:

- `run_type` — `"llm"`, `"tool"`, `"chain"` (default), `"retriever"`, `"prompt"`, `"parser"`. Sets how the run renders in the UI.
- `name` — override the display name (defaults to the function name).
- `tags` / `metadata` — static labels attached to the run (file 01).
- `project_name` — send this run's trace to a specific project.

### `wrap_openai` / `wrap_anthropic`

To trace raw provider SDK calls without decorating anything, wrap the client. Every call the wrapped client makes becomes an `llm` run with token counts and cost automatically extracted:

```python
from openai import OpenAI
from langsmith.wrappers import wrap_openai

client = wrap_openai(OpenAI())
client.chat.completions.create(model="gpt-5-mini", messages=[...])   # traced
```

There is an analogous wrapper for Anthropic:

```python
from anthropic import Anthropic
from langsmith.wrappers import wrap_anthropic

client = wrap_anthropic(Anthropic())
client.messages.create(model="claude-...", messages=[...])           # traced
```

The wrapped client is a drop-in replacement — same methods, same signatures. It also accepts `langsmith_extra` on each call for per-call tags/metadata/project, and `tracing_extra` at wrap time for defaults. Combine the two instruments freely: `wrap_openai` for the model calls, `@traceable` for the functions around them. That is the standard non-LangChain setup — a wrapped client plus a decorated pipeline function produces one clean trace.

### RunTree — manual runs

When you need to emit a run for something that is not a decoratable function boundary — a chunk of a stream, an external callback, a run whose lifetime you manage explicitly — construct a `RunTree` and post it:

```python
from langsmith.run_trees import RunTree

rt = RunTree(run_type="llm", name="OpenAI Call", inputs={"messages": messages})
completion = client.chat.completions.create(model="gpt-5-mini", messages=messages)
rt.end(outputs=completion)     # record outputs and finish timing
rt.post()                      # submit to LangSmith
```

Note a sharp edge: `RunTree` objects are **not** gated by `LANGSMITH_TRACING` or `tracing_context` — they always send when posted. Guard them yourself if you need an off switch. For nesting under a RunTree, create children with `rt.create_child(...)`.

The `trace()` context manager is the middle ground — a `with` block that creates one span without decorating a function:

```python
import langsmith as ls

with ls.trace(name="retrieval", run_type="retriever",
              inputs={"query": q}, tags=["custom"]) as rt:
    docs = my_search(q)
    rt.end(outputs={"docs": docs})
```

### Adding metadata, inputs, and outputs dynamically

Beyond the static decorator args, reach into the current run at runtime:

```python
import langsmith as ls

@ls.traceable
def handle(request):
    rt = ls.get_current_run_tree()
    rt.metadata["user_id"] = request.user_id      # set dynamically
    rt.tags.append("premium")
    ...
```

Or set defaults for a whole scope with `ls.tracing_context(metadata={...})`, or per-call with `langsmith_extra={"tags": [...], "metadata": {...}}`. If `@traceable` captures the wrong thing by default — arguments you do not want, or a return value that is not the "output" you care about — you can override what gets recorded via the decorator's processing hooks rather than logging the raw values.

### Redaction and PII

Inputs and outputs are captured verbatim, so anything sensitive in your payloads lands in the trace store unless you strip it. Options, from coarse to fine:

- **Never send payloads.** Set `LANGSMITH_HIDE_INPUTS=true` / `LANGSMITH_HIDE_OUTPUTS=true` to omit inputs/outputs entirely from all traces (you keep structure, timing, and metadata but not the content).
- **Transform before send.** Provide input/output processing functions (`process_inputs` / `process_outputs` on `@traceable`, or client-level processors) that mask fields — redact emails, drop a `password` key, hash a user id — before the data leaves your process.
- **Client-level masking.** Configure the `Client` with anonymizer/processing hooks so redaction is centralized rather than per-decorator.

The principle: decide what is allowed to enter the trace store *before* you turn tracing on in an environment that handles real user data. Redaction added after a leak does not un-leak the traces already stored.

### Sampling

Tracing every request in high-volume production is expensive and rarely necessary. Sample:

```bash
export LANGSMITH_TRACING_SAMPLING_RATE=0.1     # trace 10% of traffic
```

The sampling rate applies to `@traceable` and `RunTree` traces. Sampling is decided at the *root* — if a root run is sampled in, its whole subtree is captured; if sampled out, the entire trace is dropped — so you never get half a trace. Use a low rate in high-volume prod (you still get representative monitoring data and enough traces to build datasets from) and 100% in dev where you want to see everything.

## Why it matters

The auto-tracing story is clean until you step outside LangChain — and real systems always do: a pre-processing step, a call to a legacy service, a raw provider SDK in a hot path someone optimized. Manual instrumentation is what keeps those from being blind spots in your trace tree. A trace with a hole where the custom retriever should be is exactly the trace you will be missing when that retriever is the bug.

Redaction and sampling matter because they are what make tracing *safe* and *affordable* to leave on in production. Without redaction, tracing a user-facing app is a data-governance liability; without sampling, it is a cost and performance liability. Getting both right is the difference between "we trace prod" and "we traced prod for a week then turned it off."

## Pitfalls

- **Expecting non-LangChain code to auto-trace.** A raw `openai` call emits nothing on its own. Wrap the client or decorate the function.
- **Assuming `RunTree` respects the tracing switch.** It does not — `RunTree.post()` sends regardless of `LANGSMITH_TRACING`. Guard it yourself if you need it off in some environment.
- **Tracing PII into the store.** Verbatim inputs/outputs include whatever secrets your payloads carry. Configure redaction (`LANGSMITH_HIDE_INPUTS`/processors) *before* pointing real traffic at a project.
- **100% sampling in high-volume prod.** Full tracing at scale is costly and can add latency. Set a sampling rate; you rarely need every trace.
- **Reaching for `RunTree` when `@traceable` fits.** Manual runs are verbose and easy to get wrong (forgetting `.end()` or `.post()` yields incomplete traces). Use the decorator or wrapper unless you genuinely need manual control.
- **Losing nesting by breaking the call context.** Nesting relies on context propagation. If you hop threads or async boundaries without carrying the context, child runs detach into separate traces. Use the SDK's context helpers across those boundaries.

## Exercises

1. Instrument a plain (non-LangChain) pipeline: `wrap_openai` the client and decorate two functions with `@traceable`, one calling the other. Confirm the trace shows the inner function nested under the outer, with the LLM call as a child.
2. Give one traceable function `run_type="retriever"` and another `run_type="tool"`, and observe how each renders differently in the UI.
3. Add a `process_inputs`/redaction step (or set `LANGSMITH_HIDE_INPUTS=true`) so a `password` field never reaches the trace store, and verify it is absent from the captured run.
4. Set `LANGSMITH_TRACING_SAMPLING_RATE=0.5`, run a loop of 20 calls, and confirm roughly half produce traces. Explain why sampling is decided at the root run and what would break if it were decided per child.
5. Rewrite one `@traceable` function as an explicit `RunTree` (create, `.end()`, `.post()`), and state one reason you would *not* do this in real code.

## Further reading

- Annotate code for tracing: https://docs.langchain.com/langsmith/annotate-code
- Trace with `@traceable`: https://docs.langchain.com/langsmith/log-traces-to-project
- Trace OpenAI / wrap clients: https://docs.langchain.com/langsmith/trace-openai
- Prevent logging of sensitive data (redaction): https://docs.langchain.com/langsmith/mask-inputs-outputs
- Sample traces: https://docs.langchain.com/langsmith/sample-traces
- Add metadata and tags: https://docs.langchain.com/langsmith/add-metadata-tags
