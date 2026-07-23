# 03 · Nodes, Edges & Control Flow

## Mental model

A graph's *shape* is its control flow. You express shape with two primitives:

- **Nodes** — the actors that do work. A node is a function `State -> partial update`.
- **Edges** — how execution moves between nodes. There are two kinds:
  - **Normal edges** are unconditional: "after A, always go to B."
  - **Conditional edges** run a router function that inspects state and returns the name(s) of the next node(s).

`START` and `END` are sentinel nodes. An edge from `START` says "begin here"; an edge to `END` says "this branch is done." A run finishes when there are no more active nodes.

There is a third, more powerful way to move: a node can return a **`Command`**, which updates state *and* declares where to go in one object. Edges are static wiring you draw at build time; `Command` is dynamic routing decided at run time from inside the node. Learning when to use each is most of this chapter.

## In depth

### Normal edges

```python
builder.add_edge(START, "parse")
builder.add_edge("parse", "validate")
builder.add_edge("validate", END)
```

Straight-line flow. `parse` runs, then `validate`, then done. You can also fan out by adding several edges from one node (see parallelism below).

### Conditional edges

A conditional edge attaches a **router function** to a node. After the node runs, the router reads state and returns the next destination — a node name, `END`, or a list of names.

```python
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    value: int
    log: Annotated[list, lambda a, b: a + b]


def check(state: State) -> dict:
    return {"log": ["checked"]}


def route(state: State) -> str:
    return "big" if state["value"] > 10 else "small"


def big(state): return {"log": ["big"]}
def small(state): return {"log": ["small"]}


builder = StateGraph(State)
builder.add_node("check", check)
builder.add_node("big", big)
builder.add_node("small", small)
builder.add_edge(START, "check")
builder.add_conditional_edges("check", route)  # route returns "big" or "small"
builder.add_edge("big", END)
builder.add_edge("small", END)
graph = builder.compile()
```

The router returns a *string that matches a node name*. If your router's return values don't line up with node names, pass a mapping as the third argument: `add_conditional_edges("check", route, {"big": "big", "small": "small"})`. The mapping also documents, for visualization and validation, every possible destination.

### `Command`: update and route together

`Command` lets a node do both jobs at once — mutate state and choose the next node — which often replaces a node-plus-conditional-edge pair with a single function:

```python
from typing import Literal
from langgraph.types import Command


def check(state: State) -> Command[Literal["big", "small"]]:
    dest = "big" if state["value"] > 10 else "small"
    return Command(update={"log": ["checked"]}, goto=dest)
```

Note the return annotation `Command[Literal["big", "small"]]`. LangGraph reads it to know the node's possible destinations so it can draw and validate the graph — when a node routes via `Command`, you don't add a conditional edge for it; the annotation is how the graph learns where the node can go. Use `Command` when routing depends on work the node just did (a tool result, an LLM decision); use conditional edges when routing is a clean function of existing state. `Command` can also target a parent graph with `graph=Command.PARENT`, which is how subgraph and multi-agent handoffs jump across boundaries (chapters 9 and 10).

### Branching, loops, and the recursion limit

A **loop** is just an edge that points backward. Combine it with a conditional edge (or `Command`) that eventually routes to `END`:

```python
def step(state: State) -> dict:
    return {"value": state["value"] + 1}


def keep_going(state: State) -> str:
    return "step" if state["value"] < 5 else END


builder.add_node("step", step)
builder.add_edge(START, "step")
builder.add_conditional_edges("step", keep_going)  # loops back to "step" or exits
```

Because loops can run away, LangGraph enforces a **recursion limit** — the maximum number of super-steps in a single run (default 25). Exceed it and you get a `GraphRecursionError`. Raise it per-run through config when a legitimately long loop needs more room:

```python
graph.invoke(inputs, {"recursion_limit": 100})
```

Treat a `GraphRecursionError` as a signal first, not a number to crank up: usually it means a termination condition never fires.

### Parallel fan-out and fan-in

Add multiple edges out of one node and those targets run **in the same super-step, in parallel**. Add edges from all of them into one downstream node and that node runs once, after all parallel branches complete — a fan-in / join.

```python
builder.add_edge("dispatch", "worker_a")
builder.add_edge("dispatch", "worker_b")   # a and b run in parallel
builder.add_edge("worker_a", "collect")
builder.add_edge("worker_b", "collect")    # collect waits for both, runs once
```

For fan-in to work correctly, any key that multiple workers write must have a **reducer that combines** their writes (chapter 2). If `worker_a` and `worker_b` both write `results` and the channel uses the default replace reducer, one result vanishes; give it `operator.add` and both land.

When the number of parallel branches isn't known until run time — you want one worker per item in a list the previous node produced — use `Send`:

```python
from langgraph.types import Send


def fan_out(state: State):
    return [Send("worker", {"item": item}) for item in state["items"]]


builder.add_conditional_edges("dispatch", fan_out)
```

Each `Send` launches `worker` with its own scoped input. This is the map step of a map-reduce; the reduce step is a downstream node with an accumulating reducer.

## Why it matters

Control flow is where an agent stops being a single model call and becomes a program. Branching lets you route cheap requests away from expensive paths; loops let the model reason iteratively; parallelism cuts latency for independent work; the recursion limit is your seatbelt against infinite loops that would otherwise burn tokens forever. Choosing edges vs. `Command`, and static vs. dynamic (`Send`) fan-out, is the difference between a graph you can read on a diagram and one whose behaviour you can only discover by running it.

## Pitfalls

- **Router returns a value that isn't a node name.** Either return exact node names or pass the mapping dict so LangGraph can resolve and validate destinations.
- **Parallel writers on a replace-reducer key.** Fan-in silently drops writes unless the shared key has a combining reducer.
- **Cranking `recursion_limit` to hide a bug.** A runaway loop means a missing or wrong termination condition. Fix the condition; don't just raise the ceiling.
- **Confusing `Command(goto=...)` with edges.** If a node returns a `Command` to route, don't also add a conditional edge from it — annotate the return type with the possible destinations instead.
- **Stale-tutorial trap.** Older material routes everything through conditional edges and predates `Command` and `Send`. If a tutorial hand-builds map-reduce with manual state bookkeeping, the modern answer is `Send` plus a reducer.

## Exercises

1. Build a counter graph that loops until `value >= 5` using a conditional edge, then rebuild it using a `Command`-returning node. Compare the two for readability.
2. Create a fan-out to three workers that each append to a `results: Annotated[list, operator.add]` channel, and a `collect` node that joins them. Prove all three results survive.
3. Use `Send` to spawn one `worker` per element of an input list of arbitrary length. Verify the graph runs the right number of workers.
4. Deliberately write a loop with no exit and observe the `GraphRecursionError`. Then fix it two ways: correct the termination condition, and (separately) raise `recursion_limit`. Explain which is the real fix.

## Further reading

- Graph API — nodes, edges, conditional edges: https://docs.langchain.com/oss/python/langgraph/graph-api
- `Command` (update + route): https://docs.langchain.com/oss/python/langgraph/graph-api#command
- Map-reduce with `Send`: https://docs.langchain.com/oss/python/langgraph/graph-api#send
- Recursion limit: https://docs.langchain.com/oss/python/langgraph/graph-api#recursion-limit
