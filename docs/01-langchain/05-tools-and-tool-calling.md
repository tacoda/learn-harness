# 05 · Tools & Tool Calling

## Mental model

A tool is a **Python function the model is allowed to call**. You describe it (name, args, docstring), the model decides when to invoke it and with what arguments, your code runs it, and the result goes back as a `ToolMessage`. The model never runs code — it *emits a request* to run code, and the runtime executes it. Tool calling is the mechanism behind every agent: the loop is just "model proposes tool calls → runtime runs them → model sees results → repeat."

## In depth

### The `@tool` decorator

Decorate a function; its signature and docstring become the schema the model sees:

```python
from langchain.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's always sunny in {city}!"
```

Type hints define the argument schema; the docstring becomes the tool description; the function name becomes the tool name. All three are prompt — the model chooses tools and fills arguments based entirely on this text. Write docstrings for the model, not for humans.

For richer argument validation or descriptions, back the tool with a Pydantic schema:

```python
from pydantic import BaseModel, Field
from langchain.tools import tool

class SearchArgs(BaseModel):
    query: str = Field(description="Search terms")
    limit: int = Field(default=5, description="Max results")

@tool(args_schema=SearchArgs)
def search(query: str, limit: int = 5) -> str:
    """Search the knowledge base."""
    ...
```

### The tool-calling loop

Bind tools to a model and it may return an `AIMessage` whose `.tool_calls` list is populated instead of (or alongside) text:

```python
model_with_tools = init_chat_model("claude-sonnet-4-6").bind_tools([get_weather])
ai = model_with_tools.invoke("Weather in Boston?")
ai.tool_calls   # [{'name': 'get_weather', 'args': {'city': 'Boston'}, 'id': 'call_abc'}]
```

The raw loop is: run each requested tool, wrap its output in a `ToolMessage(tool_call_id=...)`, append to the message list, call the model again. You *can* hand-write this — but `create_agent` (module 09) runs it for you, including the **`ToolNode`**, the LangGraph node that executes a batch of tool calls and appends the results. Think of `ToolNode` as the executor half of the loop; `create_agent` wires it up automatically.

### Accessing state and context: `ToolRuntime`

A tool can read the agent's live state and per-run context by declaring a `ToolRuntime` parameter. The model does **not** see or fill it — it's injected by the runtime:

```python
from langchain.tools import tool, ToolRuntime

@tool
def get_message_count(runtime: ToolRuntime) -> str:
    """Get the number of messages in the conversation."""
    messages = runtime.state["messages"]
    return f"There are {len(messages)} messages."
```

`ToolRuntime` exposes:
- `runtime.state` — the agent's current state (messages and any custom keys),
- `runtime.context` — static per-invocation values (user id, org id) you pass at `.invoke`,
- `runtime.tool_call_id` — the id to stamp on any `ToolMessage` you build by hand.

This is the v1 replacement for the old `InjectedState` / `InjectedToolCallId` annotations — one typed parameter instead of several magic annotations.

### Returning a `Command` to update state

A tool can do more than return a value — it can **mutate the agent's state** by returning a `Command`. Use this to write extra state keys, not just append a message:

```python
from langgraph.types import Command
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage

@tool
def load_skill(skill_name: str, runtime: ToolRuntime) -> Command:
    """Load a skill's instructions into context."""
    content = fetch_skill(skill_name)
    return Command(update={
        "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
        "skills_loaded": [skill_name],   # a custom state key
    })
```

### Error handling

A tool that raises inside the loop would otherwise crash the run. Wrap tool execution with `@wrap_tool_call` middleware to convert exceptions into a `ToolMessage` the model can react to:

```python
from collections.abc import Callable
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest

@wrap_tool_call
def handle_tool_errors(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage],
) -> ToolMessage:
    """Turn tool exceptions into a message the model can recover from."""
    try:
        return handler(request)
    except Exception as e:
        return ToolMessage(
            content=f"Tool error, please adjust your input and retry. ({e})",
            tool_call_id=request.tool_call["id"],
        )
```

Feeding the error back (rather than raising) lets the model self-correct — often it retries with fixed arguments. This is the middleware pattern covered fully in module 10.

### Parallel tool calls

Models can request several tools in one turn. The runtime executes them **concurrently** and appends all the `ToolMessage`s before the next model call — no configuration needed. Design tools to be independent and side-effect-safe so parallel execution stays correct.

### Returning artifacts

Sometimes a tool produces a big blob (an image, a dataframe) that the *model* shouldn't see verbatim but *downstream code* needs. Set `response_format="content_and_artifact"` and return a `(content, artifact)` tuple: the `content` string goes to the model, the `artifact` rides along on the `ToolMessage` for your code to pull out.

```python
@tool(response_format="content_and_artifact")
def render_chart(spec: str) -> tuple[str, bytes]:
    """Render a chart and return a short caption plus the image bytes."""
    png = draw(spec)
    return "Chart rendered.", png     # model sees the caption; artifact carries the bytes
```

### Structured output as a tool

Recall from module 03 that `ToolStrategy` presents a *schema* as a synthetic tool to force a typed final answer. It's the same tool-calling machinery pointed at output shape rather than side effects — which is why tool calling is the substrate for both actions and structured results.

## Why it matters

Tools are the seam between reasoning and the world. The design choices here — schema from type hints, docstring as description, `ToolRuntime` for injected context, `Command` for state writes, middleware for errors — all serve one goal: make the model's action surface **explicit, typed, and inspectable**. Every tool call shows up in a trace with its arguments and result, so agent behavior is debuggable in a way that free-text prompting never is. The tradeoff is that tool quality lives or dies on schema clarity: a vague docstring produces a model that calls the wrong tool with the wrong arguments.

## Pitfalls

- **Docstring-free tools.** No description means the model guesses. Every tool needs a clear docstring and typed args.
- **Exposing `ToolRuntime` to the model.** It's injected, not model-filled — but only if typed as `ToolRuntime`. Mistype it and the model tries to supply it.
- **Forgetting `tool_call_id`.** Hand-built `ToolMessage`s must carry the originating call's id (`runtime.tool_call_id` / `request.tool_call["id"]`) or the loop can't match result to request.
- **Letting tools raise.** An unhandled exception aborts the run. Wrap with `@wrap_tool_call` and return a corrective `ToolMessage`.
- **Non-idempotent tools under parallel calls.** Concurrent execution can interleave side effects. Keep tools independent or serialize the risky ones.
- **Stale `InjectedState` / `InjectedToolCallId` annotations.** v1 consolidates these into `ToolRuntime`. Old-tutorial imports won't match current patterns.
- **Dumping huge blobs into `content`.** It bloats context and cost. Use `content_and_artifact` to keep bulk out of the model's view.

## Exercises

1. Write a `@tool` with typed args and a docstring; bind it and inspect `ai.tool_calls` on a prompt that should trigger it.
2. Add a tool that reads `runtime.state["messages"]` and reports the turn count.
3. Write a tool returning a `Command` that appends a `ToolMessage` and sets a custom state key; confirm the key appears in the result state.
4. Add `@wrap_tool_call` error handling and force a tool to raise; verify the model recovers instead of the run crashing.
5. Build a `content_and_artifact` tool and pull the artifact off the resulting `ToolMessage`.

## Further reading

- Tools: https://docs.langchain.com/oss/python/langchain/tools
- Tool calling & ToolNode: https://docs.langchain.com/oss/python/langchain/tools
- Agents (`create_agent`): https://docs.langchain.com/oss/python/langchain/agents
- Middleware (tool error handling): https://docs.langchain.com/oss/python/langchain/middleware
