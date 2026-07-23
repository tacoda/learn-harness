# 14 · Internals: Pregel & Channels

## Mental model

Everything in this track has been vocabulary for one engine. This chapter names it. LangGraph's runtime is **Pregel**, a bulk-synchronous-parallel (BSP) execution model borrowed from Google's graph-processing system of the same name. Strip away the `StateGraph` API and here is what's actually running:

- **Channels** are the units of state. Each top-level state key is a channel. A channel holds a value and knows how to *combine* an incoming update with its current value — that combination function is the reducer.
- **Actors** (your nodes) subscribe to channels (their inputs) and publish to channels (their outputs). An actor becomes *active* when a channel it reads has been updated.
- **Super-steps** are synchronized rounds. Each round: every active actor runs, all their writes are collected, all channels apply their updates, and the engine computes which actors are active for the next round. Repeat until no actor is active.

That's the whole engine. `StateGraph`, edges, reducers, checkpoints — all of it compiles down to actors, channels, and super-steps. Understanding this collapses a dozen separate features into one picture.

## In depth

### A super-step, precisely

The BSP discipline has three phases per step, and the discipline is the reason LangGraph behaves predictably:

1. **Compute** — every active actor runs, reading channel values *as they were at the start of the step*. No actor sees another actor's writes from the same step. This is what "synchronized" means.
2. **Communicate** — all writes from all actors are gathered.
3. **Barrier + apply** — a barrier waits for every actor to finish, then each channel applies the updates destined for it via its reducer, producing the channel values for the next step.

Because reads happen before any writes are applied, and writes are applied all-at-once at the barrier, there is **no intra-step ordering**. This is precisely why chapter 2 insisted on order-independent reducers and why chapter 3's parallel fan-in needs a combining reducer: within a step, two writes to the same channel are two updates the reducer must merge, with no "first" or "second."

### Reducers are channel update functions

A reducer isn't a special LangGraph concept bolted onto state — it *is* the channel's update semantics. The default channel is a "last value" channel: its update function discards the old value and keeps the new one (replace). `Annotated[list, operator.add]` swaps in a channel whose update function concatenates. `add_messages` is a channel whose update function reconciles messages by id. When you annotate a state key with a reducer, you are choosing which kind of channel backs that key. There are also built-in channel types beyond these (e.g. topic/ephemeral channels for transient data), but the reducer-as-channel mental model covers what you write day to day.

### What `StateGraph` compiles to

`builder.compile()` performs a translation:

- Each **node** becomes a Pregel actor: a function wrapped so it reads the state channels it needs and writes the channels it returns.
- Each **state key** becomes a channel with the reducer you declared (or the default replace channel).
- **Edges** become the subscription/triggering wiring: a normal edge `A → B` means "when A writes, make B active next step." A conditional edge attaches a router that decides which channel(s) to trigger. `START` and `END` are special channels marking entry and termination.
- The result is a `Pregel` object — the compiled runtime with `invoke`/`stream`/`get_state`.

So the graph you draw is a convenient authoring surface over a plain actor/channel network. The functional API (chapter 12) is a *different* authoring surface over the *same* Pregel runtime — which is why it has identical durability and interrupt semantics.

### How execution actually proceeds

1. Input is written to the input channels; the actors subscribed to them (those wired from `START`) become active.
2. Run a super-step: active actors compute, the barrier applies their writes to channels.
3. The writes determine the next active set (an actor whose input channel was written becomes active).
4. Repeat. When a step produces no newly-active actors, the run halts. Reaching the configured `recursion_limit` (max super-steps) aborts with an error — the seatbelt from chapter 3.

Parallelism is automatic: if a step has three active actors, they run concurrently because BSP says everything in a step runs "at once."

### Where checkpointing hooks in

The checkpointer (chapter 5) hooks the **barrier**. At the end of each super-step — after channels apply their updates, before the next step begins — the engine serializes the full set of channel values plus metadata (step number, pending writes, the next active set) and hands it to the checkpointer's `put`. That is the checkpoint. A `StateSnapshot` is just those channel values (`.values`) plus the next active set (`.next`) and metadata read back out.

This single hook explains the entire stateful feature set:

- **Resumption / durability** (ch. 5, 11): reload the last checkpoint's channel values and next-active set, continue from the barrier.
- **HITL interrupt** (ch. 7): `interrupt` raises at the barrier, leaving a valid checkpoint with a pending task; `Command(resume=...)` re-enters at that barrier.
- **Time-travel** (ch. 11): every barrier produced a checkpoint, so history is the list of barriers; `update_state` writes a *new* checkpoint (applying channel reducers) and forks.
- **Streaming** (ch. 8): `values` emits channel state at each barrier; `updates` emits the per-actor writes gathered during communicate.

They're not four subsystems — they're four views of the barrier.

### Why BSP and not an event loop

An asynchronous, any-order actor system would be more flexible but non-deterministic and far harder to checkpoint: there'd be no clean moment where "the state is consistent" to snapshot. BSP's barrier gives exactly that moment. The determinism (given fixed inputs and order-independent reducers, a graph produces the same super-step sequence) is what makes replay faithful and debugging tractable. LangGraph trades some scheduling flexibility for the ability to snapshot, resume, and replay — which is the whole value proposition of the runtime.

## Why it matters

Once you see `StateGraph` as sugar over actors and channels, the framework stops being a collection of features to memorize and becomes one mechanism to reason about. "Why did my parallel write vanish?" → two updates hit a replace channel at one barrier. "Why does resume re-run my node?" → the barrier restarts the step, and only committed channel values persist. "Why do interrupts need a checkpointer?" → the pause is a barrier snapshot. Experts debug LangGraph at this layer because every surprising behaviour has a crisp explanation in terms of channels and super-steps. It also demystifies the docs: when you read about Pregel, channels, or BSP, you now know they're describing the thing your `StateGraph` already is.

## Pitfalls

- **Reasoning about nodes as if they run in sequence within a step.** Within a super-step there is no order. Any correctness that depends on "A runs before B in the same step" is a bug; enforce ordering with edges (separate steps), not hope.
- **Treating reducers as optional decoration.** A reducer is the channel's merge function. On a parallel channel it's load-bearing; the default replace channel will drop concurrent writes.
- **Assuming state is snapshotted mid-node.** Checkpoints happen at barriers, not partway through an actor. A node's partial progress isn't persisted — only its committed writes at the barrier.
- **Ignoring the super-step count.** The recursion limit counts super-steps, not node executions or loop iterations directly. A fan-out of ten actors is still one super-step; a ten-iteration loop is ten.
- **Stale-tutorial trap.** Older material rarely explains the Pregel/BSP substrate and describes checkpointing as an add-on. In v1 the docs are explicit that LangGraph *is* a Pregel engine and channels-with-reducers are the core abstraction; read the Pregel and low-level pages for the authoritative picture.

## Exercises

1. Draw a two-node parallel fan-out/fan-in graph and annotate, for each super-step, which actors are active, what they read, and what the barrier applies. Predict the final channel values before running.
2. Give a shared fan-in channel the default replace reducer, run it, and explain the dropped write purely in channel/barrier terms. Fix it with `operator.add`.
3. Iterate `get_state_history` and match each `StateSnapshot` to a specific super-step barrier, reading `.next` as "the actors that were active going into the next step."
4. Explain to a colleague, in three sentences and using only the words actor, channel, and barrier, why HITL interrupts require a checkpointer.

## Further reading

- Pregel runtime (the engine): https://docs.langchain.com/oss/python/langgraph/pregel
- Low-level concepts — channels & reducers: https://docs.langchain.com/oss/python/langgraph/low-level
- Persistence (checkpoints at the barrier): https://docs.langchain.com/oss/python/langgraph/persistence
- Pregel (Google's original BSP graph model): https://en.wikipedia.org/wiki/Pregel_(API)
