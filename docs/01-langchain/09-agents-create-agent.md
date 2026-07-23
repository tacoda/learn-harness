# 09 · Agents with create_agent

## Mental model

`create_agent` is the v1 headline API: give it a model, some tools, and a system prompt, and it builds the **agent loop** — call the model, run any tools it requested, feed the results back, repeat until the model stops calling tools. It is the modern replacement for `AgentExecutor`, `initialize_agent`, *and* `langgraph.prebuilt.create_react_agent`. Critically, it **compiles to a LangGraph graph**: the object you get back is a graph, so everything you learn about state, streaming, checkpointers, and interrupts transfers directly. Reach for `create_agent` first for anything single-agent; drop to raw `StateGraph` only when the loop isn't the shape you need.

## In depth

### The minimal agent

```python
from langchain.agents import create_agent
from langchain.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"It's always sunny in {city}!"

agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[get_weather],
    system_prompt="You are a concise weather assistant.",
)

result = agent.invoke({"messages": [{"role": "user", "content": "Weather in SF?"}]})
print(result["messages"][-1].content)
```

Input is always `{"messages": [...]}`; output is the full state, with the final answer at `result["messages"][-1]`. The agent ran the loop — called `get_weather`, saw the result, composed the reply — with no loop code from you.

### The parameters that matter

```python
agent = create_agent(
    model="claude-sonnet-4-6",          # str or a BaseChatModel instance
    tools=[get_weather, search_docs],   # the model's action surface
    system_prompt="...",                # standing instructions
    response_format=ToolStrategy(Out),  # typed final answer (module 03)
    middleware=[...],                    # hooks into the loop (module 10)
    checkpointer=InMemorySaver(),        # per-thread memory (module 08)
    state_schema=MyState,                # custom state beyond messages
    context_schema=MyContext,            # static per-run context for tools
)
```

- **`model`** — a string (resolved by `init_chat_model`) or a pre-configured `BaseChatModel` when you need custom params or `.bind`.
- **`tools`** — plain `@tool` functions; the agent wires up the `ToolNode` and the loop.
- **`system_prompt`** — static instructions. For *dynamic* prompts (per-query, per-user) use middleware, not this field.
- **`response_format`** — makes the final message a typed object at `result["structured_response"]`.
- **`middleware`** — the extensibility seam: guardrails, summarization, HITL, dynamic prompts, retries (module 10).
- **`state_schema` / `context_schema`** — extend what flows through the graph and what tools can read via `ToolRuntime`.

### The agent loop, precisely

Each turn the compiled graph does:

1. **Model node** — call the model with the current messages (+ system prompt).
2. If the response has **no tool calls** → done; return state.
3. If it has tool calls → **tool node** runs them (in parallel), appends `ToolMessage`s, and loops back to step 1.

Middleware hooks wrap these nodes (before/after model, before/after tools) — which is why the loop is customizable without you rewriting it. The loop terminates when the model answers without requesting tools, or when a recursion limit is hit.

### State

The default state is just `{"messages": [...]}`. Extend it with a `state_schema` to carry your own fields through the loop — tools read them via `runtime.state` and write them by returning a `Command` (module 05):

```python
from langgraph.prebuilt.chat_agent_executor import AgentState

class MyState(AgentState):        # extends the built-in messages state
    skills_loaded: list[str]

agent = create_agent(model="claude-sonnet-4-6", tools=[...], state_schema=MyState)
```

### Streaming from an agent

Because the agent is a Runnable/graph, it streams — and you can choose *what* to stream (module 11 goes deep):

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "Weather in SF?"}]},
    stream_mode="updates",     # emit each step (model / tools) as it completes
):
    print(chunk)
```

`stream_mode="messages"` streams tokens; `"updates"` streams per-step state deltas (great for showing "calling get_weather…"); a list streams several modes at once.

### Async and memory

Full async (`await agent.ainvoke(...)`, `agent.astream(...)`) and per-thread memory (pass a `checkpointer` + `thread_id`, module 08) come from the graph runtime — nothing agent-specific to learn.

### When `create_agent` is enough — and when to drop down

`create_agent` is the right tool when your control flow *is* the loop: model reasons, calls tools, repeats, answers. Middleware absorbs most customization you'll actually want (guardrails, context trimming, approvals, dynamic prompts) **without leaving `create_agent`**. Drop to raw `StateGraph` only when the shape itself changes:

- branching or conditional routing between multiple distinct nodes,
- parallel fan-out/fan-in of independent sub-tasks,
- cyclic multi-actor workflows (several agents handing off),
- fine-grained interrupts at arbitrary points.

The mature progression: start with `create_agent`; add middleware as needs grow; graduate to `StateGraph` only when you hit a wall the loop plus middleware genuinely can't express. Because `create_agent` already *is* a graph, that graduation is a refactor, not a rewrite.

## Why it matters

`create_agent` collapses the 0.x zoo (`AgentExecutor`, `initialize_agent`, hand-rolled ReAct loops) into one construct that is simultaneously batteries-included *and* fully inspectable — because it's a real LangGraph graph, not an opaque executor. The design bet is that most single-agent needs are "the loop, plus a few hooks," so it makes the loop free and the hooks (middleware) first-class. The tradeoff is that the moment your problem stops being a loop, the abstraction stops helping and you must understand the graph underneath — which is exactly why this course teaches LangGraph next.

## Pitfalls

- **Copying `AgentExecutor` / `initialize_agent` from tutorials.** Dead in v1. `create_agent` replaces all of them.
- **Reaching for `StateGraph` too early.** If the loop fits, `create_agent` + middleware is less code and less to maintain. Descend only at a real wall.
- **Putting dynamic logic in `system_prompt`.** That field is static. Per-query/per-user prompts belong in middleware (dynamic prompt), not string-formatted into `system_prompt` at construction.
- **Reading the wrong output key.** Conversational answer: `result["messages"][-1]`. Typed answer: `result["structured_response"]`.
- **Expecting memory without a checkpointer.** No checkpointer → no memory across `.invoke` calls, regardless of `thread_id`.
- **Ignoring the recursion limit.** A tool loop that never satisfies the model runs until the limit and errors. Watch for models that call the same tool forever — usually a schema/description problem.
- **Assuming `create_react_agent` is still the standard.** It exists for back-compat, but `create_agent` is the v1 standard and adds the middleware system.

## Exercises

1. Build a two-tool agent and trace one run: identify each model node and tool node in the loop.
2. Add a `response_format` and read the typed result off `result["structured_response"]`.
3. Extend `state_schema` with a custom field, write it from a tool via `Command`, and confirm it appears in the final state.
4. Stream the same agent with `stream_mode="updates"` and then `"messages"`; describe what each shows.
5. Add a checkpointer + `thread_id` and hold a two-turn conversation that relies on memory.

## Further reading

- Agents (`create_agent`): https://docs.langchain.com/oss/python/langchain/agents
- Agent middleware: https://docs.langchain.com/oss/python/langchain/middleware
- Streaming: https://docs.langchain.com/oss/python/langchain/streaming
- LangGraph overview (what the agent compiles to): https://docs.langchain.com/oss/python/langgraph/overview
