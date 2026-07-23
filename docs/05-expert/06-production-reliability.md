# 06 · Production Reliability

## Mental model

A prototype agent that works 80% of the time is a demo. A production agent that works 80% of the time is an incident generator. The gap between the two is not model quality — it's **reliability engineering**: assuming every step can fail and designing so that failure is survivable, bounded, and often invisible to the user.

The organizing idea: **failure is a control-flow event, not an exception.** In a well-built agentic system, a tool timing out, a provider rate-limiting, or a process crashing are all *expected* states with defined transitions — retry, fall back, degrade, resume, or escalate. This maps directly to Loop 2 from `01-the-agent-loop-and-loop-engineering.md` (durability/recovery) and is enabled by LangGraph's core property: **state is checkpointed at every super-step**, so progress survives failure.

Four layers, inner to outer:

1. **Durability** — persist state so a crash doesn't lose work (checkpointers).
2. **Recovery** — resume, replay, or rewind to a known-good point (time travel).
3. **Resilience** — absorb transient faults automatically (retries, fallbacks, backoff, timeouts).
4. **Degradation** — when you can't succeed, fail usefully (error boundaries, graceful degradation).

## In depth

### Durability: checkpointers

Persistence is the foundation everything else stands on. Attach a checkpointer and LangGraph saves a checkpoint of state after each super-step, keyed by `thread_id`:

```python
from langgraph.checkpoint.postgres import PostgresSaver

agent = create_agent(model=..., tools=..., checkpointer=PostgresSaver(...))
agent.invoke(inputs, {"configurable": {"thread_id": "run-123"}})
```

The single most important production rule: **`InMemorySaver` / `MemorySaver` store checkpoints in RAM and lose everything on restart.** They are for development and tests only. Production wants `SqliteSaver` (single-node, file-backed) or `PostgresSaver` (multi-node, async). Getting this wrong means an agent that "works in dev" silently loses all durability in prod. See `docs/02-langgraph/05-persistence-checkpointers.md`.

Two related concerns the docs call out:

- **Checkpoint growth.** Long conversations accumulate checkpoints, raising latency and storage cost. Prune old checkpoints periodically, and keep large blobs out of state (`02-graph-engineering.md`).
- **Store vs. checkpointer.** A checkpointer is thread-scoped short-term memory; a Store is cross-thread long-term memory. Most production apps use both.

### Recovery: replay and time travel

Because state is checkpointed per step, a failed run resumes from the last completed step — re-invoke with the same `thread_id` and execution continues mid-flight, not from the top. This is *durable execution*: the system makes progress across crashes without redoing completed work.

**Time travel** goes further: you can inspect the checkpoint history of a thread, rewind to any prior checkpoint, optionally edit the state there, and re-run forward — for debugging ("what did state look like right before it went wrong?"), for correcting an agent that took a bad turn, or for exploring alternate continuations. See `docs/02-langgraph/11-durable-execution-and-time-travel.md`.

**The idempotency caveat.** Recovery *replays*. If a step performed a non-idempotent side effect (charged a card, sent an email, created a record), replaying re-executes it. Design side-effecting tools to be idempotent: accept a dedupe/idempotency key, check-before-write, or make the operation naturally repeatable. This is the one place where durability can *cause* a bug if you're careless.

### Resilience: retries, fallbacks, backoff, timeouts

Any Runnable — a model, a tool, a chain — composes with resilience wrappers:

```python
model = init_chat_model("anthropic:claude-sonnet-4-6").with_retry(
    stop_after_attempt=3,          # bounded retries
)

robust = primary_model.with_fallbacks([cheaper_model, cached_answer])
```

- **`.with_retry(...)`** handles *transient* faults (a 503, a flaky network) with automatic re-attempts and exponential backoff. Bound the attempts — an unbounded retry loop hammers a struggling provider and turns a blip into an outage.
- **`.with_fallbacks(...)`** handles *persistent* faults by degrading: primary model down → try a secondary → try a cached or canned answer. Fallbacks are how you stay up when a dependency doesn't.
- **Backoff** is not optional under rate limits. Respect `Retry-After`, back off exponentially with jitter, and — better — prevent the limit with a client-side rate limiter on the model. Reactively retrying a 429 is worse than proactively pacing.
- **Timeouts** bound every external call. A tool with no timeout can hang a run (and, without HITL-style bounding, a thread) indefinitely. Set timeouts at the tool and at the model client.

### Degradation: error handling as control flow

Don't let exceptions escape the graph — model failure as an explicit path. A tool node that fails routes, via a conditional edge, to a fallback node that either produces a degraded-but-useful result or escalates to a human (Loop 3). This makes failure *visible in the trace* and *testable* (you can unit-test the edge that routes on failure), instead of a stack trace that crashes the run. See the "error boundaries as nodes" section of `02-graph-engineering.md`.

**Graceful degradation** is the product-level version: when the agent can't fully succeed, return partial value. Retrieval down? Answer from the model's own knowledge with a caveat. One of five sections failed? Return the four that succeeded and flag the gap. The `RemainingSteps` wind-down (`01-the-agent-loop-and-loop-engineering.md`) is degradation applied to the loop budget — give a best-effort answer instead of crashing at the recursion limit.

### Deployment concerns

- **Persistence backend.** Postgres (or the managed LangGraph Platform) for anything multi-node; a single in-memory node is a single point of total data loss.
- **Statelessness of workers + shared checkpointer.** Workers should be stateless and share the checkpoint store so any worker can resume any thread. This is what makes horizontal scaling and crash recovery work.
- **Idempotent, at-least-once thinking.** Assume steps may run more than once (retries, replays, redelivery). Design tools accordingly.
- **Graceful shutdown.** The runtime exposes signals (heartbeat, control) so a node can shut down cleanly on deploy rather than being killed mid-side-effect. See `docs/02-langgraph/13-deployment-langgraph-platform.md`.
- **Observability is part of reliability.** You cannot operate what you can't see. LangSmith tracing (`docs/03-langsmith/01-tracing-and-observability.md`) and monitoring/alerts (`06-monitoring-dashboards-alerts.md`) are operational requirements, not nice-to-haves.

## Why it matters

Reliability is where agents earn the right to run business-critical work. The features are all available off the shelf in LangGraph — the failure is almost always in *not using them*: shipping `InMemorySaver`, retrying without bounds, replaying non-idempotent side effects, letting exceptions escape instead of routing them. Reliability engineering is unglamorous and it is exactly what separates a system you can put on call from one you can only demo.

## Pitfalls

- **`InMemorySaver` in production.** Total durability loss on restart, silently. Use `SqliteSaver`/`PostgresSaver`.
- **Replaying non-idempotent side effects.** Recovery re-runs steps; a card gets charged twice. Make side-effecting tools idempotent.
- **Unbounded retries.** Turns a transient provider blip into a self-inflicted outage. Always bound attempts and back off.
- **No timeouts.** A hung tool call hangs the run. Timeout every external call.
- **Exceptions as the failure path.** A stack trace that crashes the run is not a design. Route failures through explicit fallback nodes.
- **Unbounded checkpoint / state growth.** Latency and storage creep, then a cliff. Prune checkpoints; keep blobs out of state.

## Exercises

1. Take a dev agent using `InMemorySaver`, swap in `SqliteSaver`, kill the process mid-run, and re-invoke with the same `thread_id`. Confirm it resumes rather than restarts.
2. Add `.with_retry` (bounded) to a flaky tool and `.with_fallbacks` to the model. Simulate a provider outage and confirm the agent degrades instead of crashing.
3. Identify a non-idempotent tool in a system you've built and redesign it to accept an idempotency key. Prove that a replayed step does not double-execute.
4. Add an error-boundary node: on tool failure, route to a node that returns a graceful partial answer. Write a unit test for the routing edge.

## Further reading

- Persistence (checkpointers, growth, store vs. checkpointer): https://docs.langchain.com/oss/python/langgraph/persistence
- Durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- Fault tolerance / graceful shutdown: https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- LangGraph track: `docs/02-langgraph/05-persistence-checkpointers.md`, `11-durable-execution-and-time-travel.md`, `13-deployment-langgraph-platform.md`
