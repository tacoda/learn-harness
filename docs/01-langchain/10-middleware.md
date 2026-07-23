# 10 · Middleware

## Mental model

Middleware is the **v1 headline feature**: hooks that run *inside* the agent loop, at defined points, letting you intercept and modify what happens without rewriting the loop. Think of the agent loop as a pipeline — `before_model → model → after_model → tools → …` — and middleware as layers you insert at any of those seams. Everything the 0.x world did with `preModelHook`, `postModelHook`, bespoke memory classes, and hand-rolled guardrails is now one composable, ordered abstraction. It is *the* answer to "how do I customize `create_agent` without dropping to `StateGraph`."

## In depth

### The hooks

Middleware attaches logic at these points in the loop:

| Hook | Fires | Typical use |
|---|---|---|
| `before_model` | Before each model call | Trim/summarize history, inject a dynamic system prompt, log |
| `wrap_model_call` | Around the model call | Retry, fallback, rewrite the request, cache |
| `after_model` | After each model response | Guardrails on output, redaction, validation |
| `wrap_tool_call` | Around each tool call | Error handling, sandboxing, arg rewriting, HITL |

### Decorator form (single hook)

For one-off logic, decorate a function. It receives the agent state (and a `runtime` for context):

```python
from typing import Any, Callable
from langchain.agents import create_agent
from langchain.agents.middleware import (
    before_model, wrap_model_call, AgentState, ModelRequest, ModelResponse,
)
from langgraph.runtime import Runtime

@before_model
def log_before_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    print(f"About to call model with {len(state['messages'])} messages")
    return None      # return None to change nothing; return a state update to modify it

@wrap_model_call
def retry_model(request: ModelRequest,
                handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
    for attempt in range(3):
        try:
            return handler(request)
        except Exception as e:
            if attempt == 2:
                raise
            print(f"retry {attempt + 1} after {e}")

agent = create_agent(model="claude-sonnet-4-6", tools=[...],
                     middleware=[log_before_model, retry_model])
```

A `before_model` hook returning `None` is pass-through; returning a state update (e.g. `{"messages": [...]}`) modifies state before the model sees it. A `wrap_*` hook receives a `handler` it must call — wrapping it in try/except, timing, or caching is how you interpose.

### Dynamic system prompt

The most common middleware: compute the system prompt *per request* — from user context, retrieved documents, or state. This is why `system_prompt` on `create_agent` is static; anything dynamic goes here:

```python
from langchain.agents.middleware import dynamic_prompt, ModelRequest

@dynamic_prompt
def personalized_prompt(request: ModelRequest) -> str:
    user = request.runtime.context.get("user_name", "there")
    return f"You are a helpful assistant. Address the user as {user}."

agent = create_agent(model="claude-sonnet-4-6", tools=[...],
                     middleware=[personalized_prompt], context_schema=...)
```

The RAG-in-the-prompt pattern (module 07) is exactly this: retrieve inside a dynamic-prompt hook and splice the documents into the system prompt before the model runs.

### Built-in middleware

v1 ships the common needs so you don't hand-roll them:

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware, HumanInTheLoopMiddleware,
)

agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[read_email, send_email],
    middleware=[
        # Compress history when it grows too large (module 08)
        SummarizationMiddleware(model="claude-sonnet-4-6", trigger={"tokens": 4000}),
        # Pause for human approval before risky tools run
        HumanInTheLoopMiddleware(
            interrupt_on={"send_email": {"allowed_decisions": ["approve", "edit", "reject"]}},
        ),
    ],
)
```

- **`SummarizationMiddleware`** — replaces `preModelHook`-style history compaction.
- **`HumanInTheLoopMiddleware`** — pauses the loop (via a LangGraph interrupt) before designated tools, surfacing an approve/edit/reject decision. This is how you gate destructive actions.
- **Guardrail middleware** — validate or redact inputs/outputs in `before_model` / `after_model`.

### Custom class form (multi-hook, stateful)

For middleware that owns several hooks or configuration, subclass `AgentMiddleware`:

```python
from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

class PIIRedaction(AgentMiddleware):
    def before_model(self, state: AgentState, runtime: Runtime):
        return {"messages": [redact(m) for m in state["messages"]]}
    def after_model(self, state: AgentState, runtime: Runtime):
        return {"messages": [redact(state["messages"][-1])]}
```

### Composition order

Middleware is an **ordered stack**, and order is semantic. `before_*` hooks run **top-to-bottom** (list order) on the way *in*; `after_*` / `wrap_*` hooks unwind **bottom-to-top** on the way *out* — like nested function calls / an onion. So:

```python
middleware=[guardrails, summarization, retry]
# before_model:  guardrails -> summarization -> retry -> [MODEL]
# after_model:   retry -> summarization -> guardrails
```

Put outermost concerns (validation you want to run first and last) first in the list; put the model-call-adjacent concerns (retry, caching) last. Getting order wrong is a real bug — e.g. summarizing *before* redaction leaks PII into the summary.

## Why it matters

Middleware is the design decision that keeps `create_agent` viable as an abstraction. Without it, every non-trivial customization would force you down to `StateGraph`, and the high-level API would be a toy. With it, the vast majority of production needs — guardrails, context management, approvals, retries, dynamic prompts, observability — are composable layers you add declaratively, in order, without touching loop code. The tradeoff is that middleware is *ordered and stateful*, so it carries the usual middleware-stack hazards: order-dependence, hidden interactions, and layers that quietly rewrite state. Named hooks and a small vocabulary of built-ins keep that complexity legible.

## Pitfalls

- **Order-dependence ignored.** `before_*` runs list-order, `after_*`/`wrap_*` unwinds reverse-order. A redactor placed after a summarizer won't clean what the summarizer already ingested. Reason about the onion explicitly.
- **Static prompt where dynamic is needed.** Formatting per-user data into `system_prompt` at construction bakes it in for all requests. Use `dynamic_prompt` middleware instead.
- **`wrap_*` hook that forgets to call `handler`.** The model/tool never runs and the loop stalls. A wrap hook *must* invoke and return `handler(request)` (possibly guarded).
- **Hand-rolling summarization / HITL / retries.** Built-ins exist (`SummarizationMiddleware`, `HumanInTheLoopMiddleware`, `wrap_model_call` retry). Reinventing them adds untested surface.
- **Middleware doing heavy work synchronously on the hot path.** A `before_model` that makes a slow network call adds that latency to every turn. Cache, or move it off-path.
- **Stale `preModelHook` / `postModelHook` tutorials.** Those `create_react_agent` params are the 0.x/pre-middleware shape. v1 replaces both with the middleware hooks above.
- **Forgetting HITL needs a checkpointer.** `HumanInTheLoopMiddleware` interrupts the graph — resuming requires persisted state, so it needs a checkpointer + `thread_id`.

## Exercises

1. Write a `@before_model` logger and confirm it fires once per model call in a multi-tool run.
2. Add a `dynamic_prompt` hook that personalizes the system prompt from `runtime.context`, and pass context at `.invoke`.
3. Attach `HumanInTheLoopMiddleware` to a `send_email` tool (with a checkpointer); trigger the interrupt and resume with an "approve" decision.
4. Add `SummarizationMiddleware` with a low trigger and find the summarization in the trace.
5. Put two middleware in a list, log entry/exit in each, and demonstrate the onion order empirically.

## Further reading

- Middleware overview: https://docs.langchain.com/oss/python/langchain/middleware
- Custom middleware: https://docs.langchain.com/oss/python/langchain/middleware
- Human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- v1 migration (hooks → middleware): https://docs.langchain.com/oss/python/releases/langchain-v1
