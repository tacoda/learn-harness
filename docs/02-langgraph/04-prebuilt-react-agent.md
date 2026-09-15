# 04 · Prebuilt: the ReAct Agent

## Mental model

The most common agent shape is a loop: **call the model → if it asked to use tools, run them → feed results back → repeat until it stops calling tools.** This is the ReAct pattern (reason + act). It's so common that LangGraph ships it prebuilt, so you don't hand-wire the loop every time.

Two layers exist, and knowing which is which prevents a lot of confusion:

- **`langchain.agents.create_agent`** — the v1 standard. Constructs and compiles the ReAct graph for you, and adds middleware, structured output strategies, and a cleaner surface. Use this.
- **`langgraph.prebuilt.create_react_agent`** — the older LangGraph-level prebuilt. **Deprecated since LangGraph v1.0** and slated for removal in v2.0. It still runs, but every call emits a `LangGraphDeprecatedSinceV10` warning.

Both return a compiled graph, and both give you the model-tool loop with persistence, streaming, and interrupts for free — `create_agent` is the same building with a better front door. The deprecation is explicit in the LangGraph source: `create_react_agent` is decorated with `@deprecated("create_react_agent has been moved to \`langchain.agents\`. Please update your import to \`from langchain.agents import create_agent\`.")`. So even when you're living entirely in LangGraph, the agent factory you call is the LangChain one. See the [v1 migration guide](https://docs.langchain.com/oss/python/migrate/langgraph-v1).

## In depth

### `create_agent`

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"It's sunny in {city}."


agent = create_agent(
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

`ToolNode` reads the tool calls from the last AI message, runs the matching tools (in parallel when there are several), and appends the `ToolMessage` results to `messages`. It handles tool errors and injected state for you. This is exactly what `create_agent` wires in internally — LangGraph's own `ToolNode` docstring says to reach for `ToolNode` directly only when you need custom routing or non-standard error handling, and to use `create_agent` for standard ReAct agents.

### Prebuilt vs. custom graph

Use the prebuilt when your agent *is* the ReAct loop, even with some customization (a system prompt, a state modifier, pre/post hooks). Drop to a custom `StateGraph` when the shape diverges: you need a planning phase before the loop, multiple distinct model roles, non-tool branches, or a bespoke stopping rule the loop doesn't express. The good news is the transition is cheap — the prebuilt is a graph, so you can start with it and later replace one edge or node without a rewrite.

### Migrating off `create_react_agent`

For most code the migration is the import line and the function name — the parameters you care about (`model`, `tools`, `checkpointer`, `name`) carry over:

```python
# before (deprecated)
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(model=model, tools=[get_weather], name="weather")

# after
from langchain.agents import create_agent
agent = create_agent(model=model, tools=[get_weather], name="weather")
```

What you gain is the **middleware** system (summarization, guardrails, human approval, retries) wrapping the same loop, plus first-class structured output. The state class moved too: `langgraph.prebuilt.chat_agent_executor.AgentState` is deprecated in favor of `from langchain.agents import AgentState`. Anything non-trivial — custom state schemas, prompt hooks — is covered by the [v1 migration guide](https://docs.langchain.com/oss/python/migrate/langgraph-v1).

## Why it matters

Ninety percent of agents are a tool-using loop. Rebuilding that loop by hand for each one is wasted effort and a source of subtle bugs (forgetting to loop, mishandling parallel tool calls, losing tool errors). The prebuilt gives you a correct, streaming, resumable loop in a few lines, and — because it compiles to an ordinary graph — you never trade away the ability to descend and customize. Knowing that `create_agent` compiles to the same ReAct graph `create_react_agent` did is what makes the migration a one-line change and keeps everything else in this track applicable unchanged.

## Pitfalls

- **Reaching for `langgraph.prebuilt.create_react_agent`.** Deprecated since LangGraph v1.0, removal targeted for v2.0. It still runs but warns; use `langchain.agents.create_agent`.
- **Assuming the prebuilt is a black box.** It's a compiled graph. Inspect it with `get_state`, stream it, and interrupt it like any other graph.
- **Reaching for a custom graph too soon.** If you're just adding a system prompt or a post-model hook, the prebuilt (or `create_agent` middleware) already covers it.
- **Forgetting the checkpointer.** Without `checkpointer=`, the prebuilt agent is stateless across calls — each `invoke` starts fresh. Pass one and use a `thread_id` for multi-turn memory.
- **Stale-tutorial trap.** Pre-1.0 tutorials use `AgentExecutor` / `initialize_agent` from `langchain.agents`. Tutorials from the 0.x/early-1.0 window reach for `langgraph.prebuilt.create_react_agent` — closer, but now deprecated. In v1 the answer to "give me a ReAct agent" is `from langchain.agents import create_agent`. If you see `AgentExecutor`, it predates the model you want by two generations.

## Exercises

1. Build a `create_agent` with two tools and a `thread_id`, then run two turns and confirm the second turn remembers the first. Then inspect `agent.get_state(config)`.
2. Hand-build the same loop as a `StateGraph`: a model node, a `ToolNode`, and a conditional edge that loops while there are tool calls. Compare line count and behaviour to the prebuilt.
3. Take a prebuilt agent and add a node *before* the model loop that injects a system message. Note whether you needed to descend to a custom graph or could stay prebuilt.
4. Read the LangChain `create_agent` docs and list two things its middleware gives you that you'd otherwise wire by hand in a raw graph.
5. Import `create_react_agent` from `langgraph.prebuilt` and run it with `-W error::DeprecationWarning`. Read the warning text, then port the call to `create_agent`.

## Further reading

- Migrating from LangGraph v0: https://docs.langchain.com/oss/python/migrate/langgraph-v1
- LangChain `create_agent`: https://docs.langchain.com/oss/python/langchain/agents
- LangGraph prebuilt agents: https://docs.langchain.com/oss/python/langgraph/prebuilt
- `ToolNode` reference: https://docs.langchain.com/oss/python/langgraph/prebuilt#toolnode
- Agent middleware: https://docs.langchain.com/oss/python/langchain/middleware
