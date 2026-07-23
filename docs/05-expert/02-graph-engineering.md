# 02 · Graph Engineering

## Mental model

`create_agent` hands you a graph. Graph engineering is the discipline of designing that graph *deliberately* — because the moment your control flow stops being "model → tools → repeat," the graph's shape becomes the most important design decision in your system. LangGraph's own framing: nodes do the work, edges say what to do next, and **state** is the shared data structure that flows through both. "Nodes and edges are nothing more than functions." The power is not in the functions; it is in how state moves between them.

The core discipline reduces to four questions, asked in order:

1. **What is in the state?** (schema design — the contract every node reads and writes)
2. **How does state merge?** (reducers — the policy for combining concurrent writes)
3. **Where are the boundaries?** (node granularity, branches, loops, parallelism, subgraphs)
4. **How do I know it works?** (testability and observability by construction)

Everything else in this doc is an elaboration of those four. A well-engineered graph is one where the state schema is minimal, the reducers encode intent, the node boundaries are testable units, and every edge decision is observable in a trace.

## In depth

### State schema design

State is a contract. Every node declares what it reads (input schema) and what it writes; the graph state is the union of all channels. The first design question is *what belongs in state at all*. A useful triage:

- **Conversation** — the `messages` channel, almost always present, merged with `add_messages`.
- **Working data the model must see next step** — plans, retrieved documents, intermediate results. This is state's core job: carry context between super-steps.
- **Ephemeral scratch** — values a node computes and consumes within the same step. Prefer local variables; only promote to state if a *later* node needs them.
- **Control counters** — `remaining_steps`, retry counts, phase markers. Keep them separate from domain data.

LangGraph lets you split schemas so nodes see only what they need: an `input_schema`, an `output_schema` that constrains what `invoke` returns, and even **private channels** that pass data between two internal nodes without appearing in the public contract:

```python
graph = StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
```

A node can write to any channel that exists in the graph state, including a private one declared only in that node's signature. This is how you keep the public interface small while still threading internal data. (Caveat, from the docs: private channels are *not* redacted from `stream_mode="values"` — streaming emits all channels. Do not put secrets in a private channel and assume streaming hides them. See `docs/02-langgraph/02-stategraph-state-and-reducers.md`.)

**Ephemeral vs persisted.** With a checkpointer attached, *all* state is persisted at every super-step. So "ephemeral" is a design intention, not a runtime guarantee — if you don't want a large blob (a 200 KB retrieved document set) checkpointed on every step, either don't put it in state, or clear it in a `before_model`/`after_model` hook once consumed. Unbounded state growth is the most common cause of ballooning checkpoint size and latency.

### Reducers as merge policy

A reducer is the function that combines the existing channel value with a node's write. It is not plumbing — it is *policy*. The default reducer overwrites (last write wins). `add_messages` appends and de-duplicates by ID. `operator.add` concatenates lists — the workhorse for parallel fan-out where many workers each contribute to one list:

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]        # append + dedupe
    completed_sections: Annotated[list, operator.add]  # concat from parallel workers
    plan: str                                       # overwrite (last write wins)
```

The reducer choice *is* your concurrency model. If two parallel nodes both write `plan` with an overwrite reducer, one silently clobbers the other — a bug the schema should have prevented by using a list-append reducer or by not letting both write the same channel. When you design a parallel section, choose the reducer *first*, then the nodes.

### Node granularity

The instinct to make nodes tiny (one per model call) or huge (one node does everything) are both wrong. Right-sizing heuristics:

- **A node is a unit of retry and observability.** On failure the runtime replays from the start of the current super-step. Make a node the smallest chunk you'd want to retry atomically and the smallest chunk you'd want to see as one span in a trace.
- **Split at a decision or a side effect.** If a step branches on its result, or performs an irreversible action, it deserves its own node so the edge/interrupt can act on the boundary.
- **Don't split pure sequential compute.** Two transformations with no branch, no I/O, and no checkpoint value between them can live in one node.

### When to branch, loop, or parallelize

- **Branch** (`add_conditional_edges`) when the *next step depends on a result* — routing to different handlers, or looping back on failure.
- **Loop** when a step may need repeating until a condition holds (the agent loop itself; an evaluator-optimizer refine cycle). Always pair a loop with a bound (`recursion_limit`, a counter in state).
- **Parallelize** when steps are *independent*. Static parallelism = multiple edges out of one node. Dynamic parallelism = the `Send` API, which spawns a worker per item at runtime:

```python
from langgraph.types import Send

def assign_workers(state):
    return [Send("write_section", {"section": s}) for s in state["sections"]]
```

Each `Send` worker gets its own state slice; all workers write back to a shared `Annotated[list, operator.add]` channel. This is the backbone of the orchestrator-worker pattern (`04-agent-design-patterns.md`).

### Subgraph decomposition

When a region of the graph is coherent enough to name, test, and reuse, make it a **subgraph**. A subgraph is a compiled graph used as a node in a parent. Decompose when: a sub-task has its own multi-step logic; you want to test that region in isolation; or two agents in a multi-agent system each deserve their own internal graph. The interface between parent and subgraph is state channels — shared keys flow through automatically, or you map them explicitly. See `docs/02-langgraph/09-subgraphs.md`.

### Error boundaries as nodes

Production graphs make failure a *first-class path*, not an exception that escapes. Model an error boundary as an explicit node: a `try` node routes to a `fallback` node on failure via a conditional edge, and the fallback either degrades gracefully or escalates. This turns error handling into visible, testable control flow rather than a stack trace — the theme of `06-production-reliability.md`'s "error handling as control flow."

### Making graphs testable and observable

- **Testable:** because nodes are functions over state, you can unit-test a node by passing a state dict and asserting on the returned partial update — no model, no graph. Test edge functions the same way. Reserve full-graph invocation for integration tests.
- **Observable:** each node is a span in the LangSmith trace tree. Name nodes for what they *mean* ("plan_report", not "node_2") so the trace reads like a narrative. Every conditional edge's decision should be reconstructable from the trace.

### Refactoring `create_agent` → custom graph

The mature migration path is gradual, and you should resist it until forced (`docs/00-foundations/04-the-langchain-way-philosophy.md`, idiom 3). Signs it's time to descend from `create_agent` to a hand-built `StateGraph`:

- You need a node that is neither "model" nor "tools" (a deterministic planner, a retrieval step, a validation gate) in the *main* path, not just wrapping the model call.
- You need parallel fan-out (`Send`) or a cyclic sub-workflow the two-node loop can't express.
- You need multiple models as distinct actors with distinct state.

The refactor: keep `create_agent`'s inner loop as a *subgraph node* inside your larger `StateGraph`, rather than reimplementing the ReAct loop by hand. You descend one rung, not to the basement. Everything `create_agent` gave you (middleware, structured output) still applies inside that subgraph.

## Why it matters

The graph is the executable specification of your agent's control flow. A sloppy graph — god-state that everything reads and writes, overwrite reducers hiding race conditions, mega-nodes you can't test or retry, error handling via exceptions — produces an agent that is impossible to reason about and terrifying to change. A well-engineered graph is legible in a trace, testable node-by-node, and safe to extend. Graph engineering is where the "make change easy" principle meets agentic systems.

## Pitfalls

- **God-state.** One flat state dict that every node reads and writes couples everything. Use input/output/private schemas to narrow contracts.
- **Wrong reducer on a parallel channel.** Overwrite semantics + concurrent writers = silent data loss. Pick the reducer when you design the fan-out.
- **State as a dumping ground.** Large blobs left in state get checkpointed every super-step, inflating latency and storage. Clear consumed data.
- **Mega-nodes.** A node that does five things can't be retried, tested, or read in a trace granularly. Split at decisions and side effects.
- **Reimplementing the ReAct loop by hand** when descending from `create_agent`, instead of nesting it as a subgraph — you throw away middleware and structured output for no reason.

## Exercises

1. Take an existing `create_agent` and draw its compiled graph (`agent.get_graph().draw_mermaid()`). Identify the two nodes and the conditional edge, then name one node you'd add if you descended to a custom graph.
2. Design a state schema for a report-writing agent with an orchestrator and parallel section-writers. Justify the reducer on every channel.
3. Refactor a mega-node that (a) retrieves, (b) calls a model, and (c) writes to a database into three nodes. Explain what each new boundary buys you in retry and observability.
4. Add an explicit error-boundary node to a graph: a conditional edge that routes to a fallback node when a tool node fails. Write a unit test for the edge function alone.

## Further reading

- Graph API overview (state, nodes, edges, schemas, Send): https://docs.langchain.com/oss/python/langgraph/graph-api
- Workflows and agents (parallelization, orchestrator-worker): https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Persistence (what gets checkpointed): https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph track: `docs/02-langgraph/02-stategraph-state-and-reducers.md`, `03-nodes-edges-control-flow.md`, `09-subgraphs.md`
