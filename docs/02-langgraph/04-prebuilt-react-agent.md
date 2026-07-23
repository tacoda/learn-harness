# 04 · Prebuilt: the ReAct Agent

## Mental model

The most common agent shape is a loop: **call the model → if it asked to use tools, run them → feed results back → repeat until it stops calling tools.** This is the ReAct pattern (reason + act). It's so common that LangGraph ships it prebuilt, so you don't hand-wire the loop every time.

Two layers exist, and knowing which is which prevents a lot of confusion:

- **`langgraph.prebuilt.create_react_agent`** — the LangGraph-level prebuilt. Constructs and compiles the ReAct graph for you. Still present and supported in v1.
- **`langchain.agents.create_agent`** — the *new higher-level standard*, built on top of the same machinery, adding middleware, structured output strategies, and a cleaner surface. This lives in the LangChain package and is the default recommendation for single-agent apps.

Both return a compiled graph. Both give you the model-tool loop with persistence, streaming, and interrupts for free. The mental model: `create_agent` is the front door; `create_react_agent` is the same building rendered in LangGraph's own vocabulary and the thing to reach for when you're already living in LangGraph and want the prebuilt without the LangChain layer.

## In depth

### `create_react_agent`

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver


def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"It's sunny in {city}."


agent = create_react_agent(
    model="anthropic:claude-sonnet-4-5",   # or a ChatModel instance
    tools=[get_weather],
    checkpointer=InMemorySaver(),
)

config = {"configurable": {"thread_id": "1"}}
result = agent.invoke(
    {"messages": [{"role": "user", "content": "weather in Austin?"}]},
    config,
)
print(result["messages"][-1].content)
```

What you got without writing it: a `StateGraph` whose state is `{"messages": Annotated[list, add_messages]}`, a node that calls the model, a `ToolNode` that executes any tool calls, and a conditional edge that loops back to the model while there are tool calls and routes to `END` when there aren't. Because it's a normal compiled graph, `stream`, `get_state`, `interrupt`, and threads all work exactly as in the rest of this track.

### `ToolNode` on its own

`ToolNode` is the reusable piece that executes tool calls found in the latest message. You can drop it into a custom graph when you want the ReAct *tool-running* behaviour but your own control flow around it:

```python
from langgraph.prebuilt import ToolNode

tool_node = ToolNode([get_weather])
builder.add_node("tools", tool_node)
```

`ToolNode` reads the tool calls from the last AI message, runs the matching tools (in parallel when there are several), and appends the `ToolMessage` results to `messages`. It handles tool errors and injected state for you. This is exactly what `create_react_agent` wires in internally.

### Prebuilt vs. custom graph

Use the prebuilt when your agent *is* the ReAct loop, even with some customization (a system prompt, a state modifier, pre/post hooks). Drop to a custom `StateGraph` when the shape diverges: you need a planning phase before the loop, multiple distinct model roles, non-tool branches, or a bespoke stopping rule the loop doesn't express. The good news is the transition is cheap — the prebuilt is a graph, so you can start with it and later replace one edge or node without a rewrite.

### Relationship to `create_agent`

`create_agent` (LangChain) is where the ecosystem is investing: it adds a **middleware** system (summarization, guardrails, human approval, retries) that wraps the same loop, and first-class structured output. For a new single-agent project, prefer `create_agent`; reach for `create_react_agent` when you're operating purely inside LangGraph, want the leanest prebuilt, or are following LangGraph-native docs. They are close cousins, not competitors — under the hood both are the ReAct graph.

## Why it matters

Ninety percent of agents are a tool-using loop. Rebuilding that loop by hand for each one is wasted effort and a source of subtle bugs (forgetting to loop, mishandling parallel tool calls, losing tool errors). The prebuilt gives you a correct, streaming, resumable loop in a few lines, and — because it compiles to an ordinary graph — you never trade away the ability to descend and customize. Knowing that `create_agent` and `create_react_agent` are the *same graph* at different altitudes lets you move between them without relearning anything.

## Pitfalls

- **Assuming the prebuilt is a black box.** It's a compiled graph. Inspect it with `get_state`, stream it, and interrupt it like any other graph.
- **Reaching for a custom graph too soon.** If you're just adding a system prompt or a post-model hook, the prebuilt (or `create_agent` middleware) already covers it.
- **Forgetting the checkpointer.** Without `checkpointer=`, the prebuilt agent is stateless across calls — each `invoke` starts fresh. Pass one and use a `thread_id` for multi-turn memory.
- **Stale-tutorial trap.** Pre-1.0 tutorials use `AgentExecutor` / `initialize_agent` from `langchain.agents`, or import `create_react_agent` from moved paths. In v1 the LangGraph prebuilt is `langgraph.prebuilt.create_react_agent`, and the recommended high-level entry is `langchain.agents.create_agent`. If you see `AgentExecutor`, it predates the model you want.

## Exercises

1. Build a `create_react_agent` with two tools and a `thread_id`, then run two turns and confirm the second turn remembers the first. Then inspect `agent.get_state(config)`.
2. Hand-build the same loop as a `StateGraph`: a model node, a `ToolNode`, and a conditional edge that loops while there are tool calls. Compare line count and behaviour to the prebuilt.
3. Take a prebuilt agent and add a node *before* the model loop that injects a system message. Note whether you needed to descend to a custom graph or could stay prebuilt.
4. Read the LangChain `create_agent` docs and list two things its middleware gives you that you'd otherwise wire by hand in a raw graph.

## Further reading

- LangGraph prebuilt agents: https://docs.langchain.com/oss/python/langgraph/prebuilt
- `ToolNode` reference: https://docs.langchain.com/oss/python/langgraph/prebuilt#toolnode
- LangChain `create_agent`: https://docs.langchain.com/oss/python/langchain/agents
- Agent middleware: https://docs.langchain.com/oss/python/langchain/middleware
