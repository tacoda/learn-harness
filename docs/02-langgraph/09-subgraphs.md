# 09 · Subgraphs

## Mental model

A **subgraph** is a compiled graph used as a node inside another graph. It's how you compose: build a self-contained piece of behaviour once, then drop it into larger graphs without rewiring its internals. The same idea scales all the way up to multi-agent systems (chapter 10), where each agent is a subgraph.

The one thing you must get right is **how state crosses the boundary**. There are two cases:

1. **Shared schema** — parent and subgraph share state keys. Updates flow through transparently: the subgraph reads and writes the same channels as the parent. Simplest, and the default when you add a compiled graph directly as a node.
2. **Isolated schema** — the subgraph has its own state shape. You must *transform* state at the boundary: map parent state into the subgraph's input, and map the subgraph's output back into parent state. This keeps the subgraph reusable and its internals private.

Choosing between them is a coupling decision: shared schema is convenient but ties the subgraph to the parent's state; isolated schema is more work but makes the subgraph a true black box.

## In depth

### Shared-schema subgraph: add it as a node directly

When the subgraph's state schema shares the keys it needs with the parent, compile it and hand the compiled object straight to `add_node`:

```python
# Subgraph shares the `messages` channel with the parent.
sub_builder = StateGraph(State)
sub_builder.add_node("summarize", summarize)
sub_builder.add_edge(START, "summarize")
sub_builder.add_edge("summarize", END)
subgraph = sub_builder.compile()

# Parent uses the compiled subgraph as a single node.
parent = StateGraph(State)
parent.add_node("sub", subgraph)     # the whole subgraph is one node
parent.add_edge(START, "sub")
parent.add_edge("sub", END)
graph = parent.compile()
```

The subgraph runs as one step from the parent's perspective; internally it takes its own super-steps. Because the schema is shared, whatever the subgraph writes to `messages` lands in the parent's `messages`.

### Isolated-schema subgraph: transform at the boundary

When the subgraph has a different state shape, you can't add it directly — the parent doesn't know how to feed it. Wrap it in a node function that translates in and out:

```python
class SubState(TypedDict):     # subgraph's private shape
    query: str
    answer: str


subgraph = sub_builder.compile()   # expects SubState


def call_sub(state: ParentState) -> dict:
    # Map parent state -> subgraph input.
    sub_in = {"query": state["question"]}
    sub_out = subgraph.invoke(sub_in)
    # Map subgraph output -> parent state.
    return {"result": sub_out["answer"]}


parent.add_node("sub", call_sub)
```

The wrapper is the boundary contract: it's the only place that knows both schemas. Change either schema and you fix one function, not the whole graph. This is how you keep a subgraph genuinely reusable across parents that store their data differently.

### When to use which

- **Shared** when the subgraph is a logical extension of *this* graph and you want frictionless state flow — e.g. a sub-pipeline that operates on the same conversation.
- **Isolated** when the subgraph is a reusable component with its own concerns — a retrieval module, a scoring routine, an agent you'll reuse elsewhere. The transformation cost buys you decoupling.

### Handoffs across the boundary with `Command`

A subgraph node can route to the *parent* graph using `Command(graph=Command.PARENT, goto=...)`. This is how a nested agent hands control back up or over to a sibling — the basis of the multi-agent handoffs in chapter 10. It's the escape hatch when a subgraph needs to affect control flow beyond its own scope.

### Streaming from subgraphs

By default, streaming (chapter 8) surfaces only the parent's events; a subgraph running as a node looks like one opaque step. Pass `subgraphs=True` to `stream`/`astream` to see inside:

```python
for ns, chunk in graph.stream(inputs, config, stream_mode="updates", subgraphs=True):
    print(ns, chunk)   # ns is the namespace path identifying the subgraph
```

The namespace path tells you which subgraph (and how deeply nested) produced each event — essential for debugging and for UIs that show nested agent activity.

### Persistence composes

You compile the *parent* with a checkpointer; subgraphs participate in the same checkpointing automatically. You don't attach separate checkpointers to subgraphs used as nodes — the parent's checkpointer captures the whole composed run, so resumption and time-travel work across the boundary.

## Why it matters

Composition is how systems stay maintainable as they grow. Without subgraphs you'd inline every capability into one enormous graph that's impossible to test or reuse; with them you build and verify pieces in isolation and assemble them with confidence. The shared-vs-isolated distinction is the single most important design lever here: it determines whether your components are reusable black boxes or convenient-but-coupled extensions. And because subgraphs are just graphs, everything you know — state, reducers, streaming, persistence — applies unchanged at every level of nesting.

## Pitfalls

- **Adding an isolated-schema subgraph directly as a node.** If the schemas don't share the needed keys, the subgraph gets no input or the wrong input. Wrap it in a transforming node.
- **Assuming shared state when it isn't.** Two graphs with different key names don't magically align. Verify the channels actually overlap before relying on transparent flow.
- **Attaching a checkpointer to a subgraph used as a node.** Compile the parent with the checkpointer; the subgraph inherits it. Double-checkpointing causes confusion.
- **Not passing `subgraphs=True` when debugging.** If a subgraph "does nothing visible," you're probably just not streaming its internal events.
- **Over-sharing state.** Sharing every key couples the subgraph to the parent and defeats reuse. Share only what the boundary genuinely needs; isolate the rest.
- **Stale-tutorial trap.** Older examples inline everything or use ad-hoc function calls between graphs instead of compiled subgraphs and boundary transforms. The v1 pattern is compiled-graph-as-node plus a wrapper for schema translation, and `Command(graph=Command.PARENT)` for upward handoffs.

## Exercises

1. Build a shared-schema subgraph that appends to `messages` and use it as a node in a parent. Confirm the parent's `messages` reflect the subgraph's work.
2. Build an isolated-schema subgraph (`{"query", "answer"}`) and integrate it into a parent whose state uses `{"question", "result"}` via a transforming wrapper node. Verify the mapping both directions.
3. Stream the parent with and without `subgraphs=True` and describe what extra events appear and how the namespace path reads.
4. Have a subgraph node return `Command(graph=Command.PARENT, goto="other")` and trace how control leaves the subgraph. Explain when you'd want this.

## Further reading

- Subgraphs guide: https://docs.langchain.com/oss/python/langgraph/subgraphs
- Adding and transforming subgraph state: https://docs.langchain.com/oss/python/langgraph/subgraphs#add-a-subgraph
- Streaming from subgraphs: https://docs.langchain.com/oss/python/langgraph/streaming#subgraphs
- `Command` to parent graph: https://docs.langchain.com/oss/python/langgraph/graph-api#command
