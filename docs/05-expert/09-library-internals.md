# 09 · Library Internals

## Mental model

To debug and extend the stack you need a source-level mental model of what your agent *actually is* when it runs. Four ideas compose the whole thing:

1. **`create_agent` is not a runtime — it's a graph builder.** It compiles down to a LangGraph `StateGraph`. The "agent" is a graph.
2. **Everything is a Runnable.** Models, tools, prompts, parsers, and compiled graphs all implement one interface. That interface is why they compose.
3. **LangGraph is a Pregel engine.** It executes graphs as message-passing over channels in discrete super-steps (BSP — bulk synchronous parallel).
4. **Persistence, streaming, interrupts, and middleware all hook the super-step boundary.** They are not bolted on; they are consequences of the execution model.

Once these four click, the stack stops being magic. A confusing behavior — why did this run twice? why didn't my state update appear? why did streaming emit a channel I marked private? — resolves into "what happens at the super-step boundary," every time.

## In depth

### `create_agent` compiles to a graph

When you call `create_agent(model, tools, middleware=...)`, you get back a *compiled LangGraph graph* — a Runnable. The graph shape, at its core, is:

```
        ┌─────────────┐
START ─▶ │    model    │ ──(no tool calls)──▶ END
        └─────────────┘
           │      ▲
   (tool calls)   │ (tool results)
           ▼      │
        ┌─────────────┐
        │    tools    │
        └─────────────┘
```

A **model node**, a **tools node**, and a conditional edge that loops back to the model after tools run or exits when the model stops calling tools. That loop is the ReAct pattern (`01-the-agent-loop-and-loop-engineering.md`). Structured output (`response_format`) and middleware add nodes/wrappers around this core, but the skeleton is this two-node cycle. You can see it: `agent.get_graph().draw_mermaid()`. This is why "learning LangGraph is learning what your agent actually is" (`docs/00-foundations/01-overview-and-mental-model.md`) — `create_agent` is a convenient constructor for a graph you could build by hand.

### The Runnable protocol as the universal interface

Every composable piece implements `Runnable` (defined in `langchain-core`): `.invoke`, `.stream`, `.batch`, and their async twins. This single contract is the load-bearing abstraction of the entire ecosystem:

- It's why `prompt | model | parser` works — `|` composes Runnables into a `RunnableSequence`.
- It's why a LangGraph node can call a model, a tool, or an entire sub-chain interchangeably — they're all Runnables.
- It's why `.with_retry()` and `.with_fallbacks()` work on *anything* — they're methods on the Runnable interface (`06-production-reliability.md`).
- It's why a plain Python function used as a node gets batch, async, and tracing for free — LangGraph wraps it in a `RunnableLambda`.

Learn the Runnable contract once (`docs/01-langchain/04-runnables-and-lcel.md`, `13-implementing-custom-components.md`) and the whole library collapses into one shape.

### The Pregel / BSP engine

LangGraph's executor is modeled on Google's **Pregel** and runs **bulk synchronous parallel (BSP)** computation. The docs put it plainly: "LangGraph's underlying graph algorithm uses message passing to define a general program. When a node completes, it sends messages along one or more edges to other nodes. These recipient nodes execute their functions, pass the resulting messages onward, and the process continues."

The pieces:

- **Channels** are the state — each key in your state schema is a channel with a reducer (`02-graph-engineering.md`).
- **Actors** are the nodes — functions that read channels and write channel updates.
- **Super-steps** are the unit of execution. In each super-step: all nodes with pending input run (potentially in parallel), their writes are collected, reducers merge them into the channels, and the runtime computes which nodes are triggered for the *next* super-step. Then the boundary is crossed and it repeats.

The BSP property that matters: **within a super-step, nodes run concurrently and don't see each other's writes; writes are only visible after the boundary, once reducers have merged them.** This is *why* the reducer on a parallel channel matters so much — concurrent writers in the same super-step all land through the reducer at the boundary. It's also why `recursion_limit` counts super-steps: it's the natural unit of "how far has this run progressed." See `docs/02-langgraph/14-internals-pregel-channels.md`.

LangGraph exposes three APIs over this one engine (per Harrison Chase's framework essay): the **declarative Graph API** (`StateGraph`, nodes and edges — the recommended mental model), the **functional API** (`@task`/`@entrypoint` — imperative style, same engine underneath, `docs/02-langgraph/12-functional-api.md`), and the lower-level **Pregel/event-driven API**. They're three front-ends to the same BSP executor — which is why LangGraph is, in his framing, "a blend of declarative and imperative," not purely one.

### How checkpointing, streaming, and interrupts hook the super-step boundary

The super-step boundary is the universal hook point. Everything durable happens there:

- **Checkpointing.** The checkpointer writes a snapshot of all channels *at each super-step boundary*. That's why recovery resumes from the last completed super-step, and why `recursion_limit` (in super-steps) and checkpoint frequency align. Time travel is just "load the channels from an earlier checkpoint and resume the engine from there" (`06-production-reliability.md`).
- **Streaming.** The engine emits events at boundaries — `values` mode streams the full channel set after each step, `updates` mode streams just what changed. This also explains a documented gotcha: `stream_mode="values"` emits *all* channels including private ones, because streaming operates on the channel set, not the output schema (`02-graph-engineering.md`). Streaming isn't a wrapper around the model; it's a view onto the engine's boundaries.
- **Interrupts.** An `interrupt()` halts the engine *at a boundary*, checkpoints, and returns control. `Command(resume=...)` re-enters the engine at that saved boundary, feeding the resume value back into the paused node. This is why human-in-the-loop requires a checkpointer (`01-the-agent-loop-and-loop-engineering.md`, Loop 3) — the interrupt has to persist the boundary to resume from it.

One boundary, four capabilities. Internalize "the super-step boundary is where durability lives" and durable execution, streaming, time travel, and HITL all stop being separate features.

### How middleware wraps the loop

Middleware is the extension mechanism for `create_agent`'s loop, and it works by wrapping the model and tool calls at defined hook points rather than by editing the graph:

- **`before_model` / `after_model`** run before/after the model node; they can read and *persistently* update state (e.g. trim messages before the call, record something after).
- **`wrap_model_call`** wraps the model invocation itself — it can make *transient* changes (alter the messages sent for this one call without touching state) and, if it returns an `ExtendedModelResponse` with a `Command`, persistent ones too.
- **`wrap_tool_call`** wraps tool execution — clip a large result, short-circuit a redundant call, inject a synthetic result.
- **`@dynamic_prompt`** computes the system prompt per call from runtime context.

The transient-vs-persistent distinction (`03-context-engineering.md`) falls straight out of *where* the hook sits relative to the state channels: wrapping the call shapes the input transiently; the lifecycle hooks write to channels persistently. Middleware composes (a list, applied in order) and keeps you on the high-level path instead of forking the graph — the v1 idiom (`docs/00-foundations/04-the-langchain-way-philosophy.md`, idiom 6; `docs/01-langchain/10-middleware.md`).

## Why it matters

You will hit behavior that makes no sense until you know the internals: a state update that "didn't take" (you read a channel in the same super-step it was written), a step that "ran twice" (a replay after a boundary), a private channel leaking into a stream (streaming emits channels, not the output schema), a middleware change that persisted when you wanted it transient (wrong hook). Every one of these is obvious once you hold the four-idea model. Internals knowledge is what lets you *debug* the stack instead of cargo-culting around it, and what lets you *extend* it — write custom middleware, custom channels, custom nodes — with confidence that you know what the engine will do.

## Pitfalls

- **Expecting writes to be visible within the same super-step.** Concurrent nodes don't see each other's writes until the boundary merges them. Sequence dependent steps across super-steps.
- **Assuming private channels are hidden from streaming.** `stream_mode="values"` emits all channels. Don't rely on private channels for secrecy.
- **Reimplementing the ReAct loop by hand** when you could nest `create_agent`'s compiled graph as a node (`02-graph-engineering.md`). You'd be rebuilding the engine's job.
- **Treating middleware hooks as interchangeable.** `wrap_model_call` (transient) and `before_model` (persistent) have different effects on state. Pick by where the hook sits.
- **Forgetting the checkpointer for interrupts.** Interrupts persist the boundary; no checkpointer, no resume.

## Exercises

1. Build a `create_agent`, call `agent.get_graph().draw_mermaid()`, and identify the model node, tools node, and the conditional edge. Predict how the shape changes when you add `response_format`.
2. Write a graph with two parallel nodes that both write the same channel. Observe how the reducer merges them at the boundary, then change the reducer and re-run. Explain the difference in terms of super-steps.
3. Stream a graph with `stream_mode="values"` and `stream_mode="updates"`. Explain what each shows in terms of the engine's boundary behavior, and demonstrate the private-channel-leak gotcha.
4. Write one `wrap_model_call` middleware (transient) and one `before_model` middleware (persistent) that both trim messages. Show in a trace how their effect on saved state differs.

## Further reading

- Graph API overview (message passing, Pregel, channels, schemas): https://docs.langchain.com/oss/python/langgraph/graph-api
- How to think about agent frameworks (the three APIs over one engine): https://blog.langchain.com/how-to-think-about-agent-frameworks/
- Middleware: https://docs.langchain.com/oss/python/langchain/middleware
- LangGraph track: `docs/02-langgraph/14-internals-pregel-channels.md`, `12-functional-api.md`
- LangChain track: `docs/01-langchain/04-runnables-and-lcel.md`, `13-implementing-custom-components.md`
