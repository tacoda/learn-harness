# 01 · Why LangGraph & the Mental Model

## Mental model

A chain is a straight line: input flows through a fixed sequence of steps and out the other end. LangGraph is a **directed graph of actors that share state and run in discrete steps**. The difference is not cosmetic — it's the difference between a pipeline and a program with control flow.

Three ideas carry almost everything in LangGraph:

1. **State is shared and explicit.** There is one state object. Every node reads from it and returns updates to it. Nothing is passed positionally between nodes — you route by editing state.
2. **Execution proceeds in super-steps.** LangGraph is a Pregel / bulk-synchronous-parallel (BSP) engine. In each super-step, every currently-active node runs (possibly in parallel), *then* all their updates are applied to state at once, *then* the engine decides which nodes run next. Nodes never see each other's half-written state within a step.
3. **Every super-step boundary is a durable checkpoint.** Because updates land at well-defined moments, the engine can snapshot state at each boundary. That snapshot is what makes persistence, resumption, human-in-the-loop, and time-travel possible — they are all consequences of the same mechanism.

If `create_agent` (LangChain's batteries-included agent) is a prebuilt car, LangGraph is the chassis, engine, and transmission. You descend to it when you need to build something the prebuilt car can't be configured into.

## In depth

Here is the smallest complete graph. It shows every core piece: state with a reducer, nodes that return partial updates, edges, and compilation.

```python
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list, add_messages]


def call_model(state: State) -> dict:
    # In a real graph this calls an LLM; here we just echo.
    last = state["messages"][-1]
    return {"messages": [{"role": "assistant", "content": f"echo: {last['content']}"}]}


builder = StateGraph(State)
builder.add_node("model", call_model)
builder.add_edge(START, "model")
builder.add_edge("model", END)
graph = builder.compile()

result = graph.invoke({"messages": [{"role": "user", "content": "hi"}]})
print(result["messages"][-1]["content"])  # echo: hi
```

Read that carefully, because the vocabulary recurs in every later chapter:

- **`State`** is a `TypedDict`. The `Annotated[list, add_messages]` says: the `messages` key is a channel whose updates are merged by the `add_messages` reducer (append new messages, replace by id) rather than overwritten.
- **A node** is just a function `State -> dict`. It returns a *partial* update, not the whole state. The engine merges that partial into state using each key's reducer.
- **Edges** wire nodes together. `START` and `END` are sentinel nodes marking where execution enters and leaves.
- **`compile()`** turns the builder into a runnable `Pregel` object with `.invoke`, `.stream`, `.get_state`, and friends.

### When to descend from `create_agent`

Start high. `create_agent` (see the LangChain track) gives you the model-tool loop, structured output, and middleware in a few lines, and it *compiles down to a LangGraph graph anyway*. Descend to `StateGraph` when you need control the high-level API can't express:

| Need | Why `create_agent` isn't enough |
|---|---|
| Branching on custom conditions | The agent loop is model→tools→model; you want your own routing |
| Cyclic reasoning with bespoke stopping | You need to own the loop and its termination |
| Parallel fan-out / fan-in | Run N nodes concurrently and join their results |
| Fine-grained interrupts mid-flow | Pause at an arbitrary point, not just around tool calls |
| Multiple cooperating agents with shared state | Model a network/supervisor/swarm topology |
| Durable long-running workflows | Checkpoint and resume across process restarts |

The honest rule: if you can describe your app as "call the model, let it use tools, repeat until done," use `create_agent`. The moment you're drawing boxes and arrows on a whiteboard, you want a graph.

### The actor / super-step picture

Think of each node as an **actor** that wakes when it has input on its incoming channels, does work, and writes to outgoing channels. A super-step is one synchronized round: all awake actors fire, all writes are collected, all reducers apply, and the engine computes the next wake set. This is why two parallel nodes writing the same key need a reducer that can combine both writes — there is no "last writer wins" ordering within a step, because there is no ordering within a step. (Chapter 14 opens this engine up completely.)

### Durable, stateful execution

Attach a checkpointer and every super-step boundary is persisted against a `thread_id`:

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "conversation-1"}}
graph.invoke({"messages": [{"role": "user", "content": "hi"}]}, config)
graph.invoke({"messages": [{"role": "user", "content": "again"}]}, config)
# The second call sees the first call's messages — state is durable per thread.
```

That single `checkpointer=` argument is the seam through which persistence (ch. 5), memory (ch. 6), human-in-the-loop (ch. 7), and time-travel (ch. 11) all enter. Learn the mechanism once and those chapters become variations on a theme.

## Why it matters

Every reliable agent eventually needs the same four things: to branch, to loop, to pause for a human, and to survive a crash. Chains give you none of these; you end up reimplementing them badly in application code. LangGraph makes them first-class and, crucially, makes them *composable* — because they all fall out of one uniform model (shared state + super-steps + checkpoints), they interoperate instead of fighting. Understanding that this is *what your agent already is* — even when you wrote it with `create_agent` — is what lets you reason about failures, cost, and latency instead of guessing.

## Pitfalls

- **Reaching for `StateGraph` too early.** Most single-agent apps fit `create_agent`. Writing a hand-rolled graph for them is more code to maintain for no capability gain.
- **Thinking of nodes as function calls.** They are actors that communicate through state channels, not subroutines you pass arguments to. "How do I pass X to the next node?" is answered by "put X in state," never by a return-then-argument handoff.
- **Assuming within-step ordering.** In a parallel super-step there is no "this node runs before that one." If two nodes write the same key, define a reducer that combines them or you'll lose a write.
- **Stale-tutorial trap.** Pre-1.0 material leans on `AgentExecutor` and treats LangGraph as exotic. In v1, LangGraph is the runtime under everything, and `create_agent` (LangChain) is the standard high-level entry. Tutorials built on `langgraph.prebuilt.create_react_agent` still run, but that function is deprecated as of LangGraph v1.0 (chapter 4). Check imports before trusting code.

## Exercises

1. Take the minimal graph above and add a second node `shout` that uppercases the last message. Wire `model → shout → END`. Verify the output changes and articulate which channel each node writes.
2. Without running it, predict what `graph.get_state(config)` returns after two invocations on the same `thread_id`. Then run it and check.
3. Write one sentence each describing a real app you'd build with (a) `create_agent`, (b) a hand-rolled `StateGraph`. Name the specific capability that forces the second one down to the graph level.

## Further reading

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- Graph API concepts: https://docs.langchain.com/oss/python/langgraph/graph-api
- Why LangGraph (design rationale): https://docs.langchain.com/oss/python/langgraph/why-langgraph
- Pregel / runtime model: https://docs.langchain.com/oss/python/langgraph/pregel
