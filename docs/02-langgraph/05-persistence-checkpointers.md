# 05 · Persistence & Checkpointers

## Mental model

A **checkpointer** is the component that saves graph state at every super-step boundary. Attach one at compile time and the graph becomes *durable*: its state survives across invocations and process restarts, keyed by a `thread_id`.

Three terms, precisely:

- **Super-step** — one synchronized round of the engine (chapter 1). The checkpointer writes a snapshot at the *end* of each one.
- **Checkpoint** — one such snapshot: the full channel values plus metadata, identified by a `checkpoint_id`.
- **Thread** — a sequence of checkpoints sharing a `thread_id`. A thread is "one conversation" or "one run's history."

The picture: a thread is a timeline; each super-step drops a save-point on it; `thread_id` picks the timeline and (optionally) `checkpoint_id` picks a point on it. Everything stateful in LangGraph — multi-turn memory, human-in-the-loop, time-travel, crash recovery — is this one mechanism used differently.

## In depth

### Turning persistence on

```python
from langgraph.checkpoint.memory import InMemorySaver

graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "user-42"}}
graph.invoke({"messages": [{"role": "user", "content": "my name is Ian"}]}, config)
graph.invoke({"messages": [{"role": "user", "content": "what's my name?"}]}, config)
# The second call sees the first call's state because both share thread_id "user-42".
```

No `thread_id` and the checkpointer has nothing to key on — you'll get an error or a fresh state each call. The `thread_id` *is* the handle to durable state.

### Choosing a checkpointer

| Saver | Import | Use for |
|---|---|---|
| `InMemorySaver` | `from langgraph.checkpoint.memory import InMemorySaver` | Dev, tests, notebooks. Lost on process exit. |
| SQLite saver | `langgraph-checkpoint-sqlite` → `from langgraph.checkpoint.sqlite import SqliteSaver` (async: `AsyncSqliteSaver`) | Single-node apps, local durability, small scale. |
| Postgres saver | `langgraph-checkpoint-postgres` → `from langgraph.checkpoint.postgres import PostgresSaver` (async: `AsyncPostgresSaver`) | Production, multi-node, concurrent threads. |

The SQLite and Postgres savers are separate installable packages. They share the `BaseCheckpointSaver` interface, so swapping `InMemorySaver()` for a `PostgresSaver` is a one-line change — your graph code doesn't change at all. The Postgres saver typically needs a one-time `.setup()` to create its tables:

```python
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@localhost:5432/db"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # first run only: creates checkpoint tables
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke(inputs, {"configurable": {"thread_id": "1"}})
```

### Inspecting state: `get_state`

`get_state(config)` returns a **`StateSnapshot`** for the latest checkpoint of a thread:

```python
snap = graph.get_state(config)
snap.values       # the channel values (your state dict)
snap.next         # tuple of nodes queued to run next (empty if the run finished)
snap.config       # includes the checkpoint_id of this snapshot
snap.metadata     # step number, source, writes
snap.tasks        # pending tasks, including any interrupts
```

`snap.next` is the key to resumption: if it's non-empty, the graph is paused mid-run (e.g. at an interrupt) and calling `invoke(None, config)` will continue from there. If it's empty, the run completed.

### Walking history: `get_state_history`

`get_state_history(config)` yields every checkpoint on the thread, newest first:

```python
for snap in graph.get_state_history(config):
    print(snap.metadata["step"], snap.next, list(snap.values.keys()))
```

Each snapshot carries its own `checkpoint_id`. Pin one in config to read or resume from that exact point:

```python
past = {"configurable": {"thread_id": "user-42", "checkpoint_id": "<id-from-history>"}}
graph.get_state(past)          # state as of that checkpoint
graph.invoke(None, past)       # resume/replay from that checkpoint (see chapter 11)
```

This history is the substrate for time-travel and forking, covered in chapter 11.

### Resuming after a pause or crash

Because state is persisted per super-step, an interrupted or crashed run leaves a valid checkpoint. To continue, call the graph again with the same `thread_id` and `None` as input — the engine reads the last checkpoint, sees `next`, and picks up where it stopped. This is the same call you use to resume a human-in-the-loop interrupt (chapter 7); persistence is what makes it possible.

## Why it matters

Persistence is the feature that turns a graph from a stateless function into a durable service. It's the prerequisite for memory (the model remembers earlier turns), for human-in-the-loop (a run can pause for hours and resume), and for reliability (a crashed worker resumes from the last checkpoint instead of restarting). The design choice — snapshot at every super-step boundary — is why all of these compose cleanly: they're all reading and writing the same checkpoint timeline. Picking the right saver (in-memory for dev, Postgres for prod) is a deployment decision, not a code decision, precisely because they share one interface.

## Pitfalls

- **Compiling with a checkpointer but forgetting `thread_id`.** With no thread to key on, state doesn't persist between calls. Always pass `{"configurable": {"thread_id": ...}}`.
- **Shipping `InMemorySaver` to production.** It vanishes on restart and doesn't share across processes. Use SQLite or Postgres for anything durable.
- **Not calling `.setup()` on the Postgres/SQLite saver.** The first run needs its tables created, or you get missing-relation errors.
- **Mixing sync and async savers.** If you drive the graph with `ainvoke`/`astream`, use the async saver (`AsyncPostgresSaver`, `AsyncSqliteSaver`) or you'll hit event-loop errors.
- **Assuming a checkpoint stores your objects verbatim.** State is serialized. Keep state values serializable; don't stash open connections or un-picklable handles in state.
- **Stale-tutorial trap.** Older code imports `MemorySaver` from `langgraph.checkpoint.memory`; the current dev saver is `InMemorySaver`. Some 0.x tutorials also use callback-based memory classes from LangChain — in v1, memory is checkpointers plus `thread_id`.

## Exercises

1. Compile a graph with `InMemorySaver`, run two turns on one `thread_id`, then run one turn on a different `thread_id`. Show that the threads are independent.
2. Swap `InMemorySaver` for `SqliteSaver` pointed at a file. Kill the process, restart, and confirm the earlier state is still there for the same `thread_id`.
3. Print `get_state(config).next` immediately after a completed run and after a run you interrupt (chapter 7). Explain the difference.
4. Iterate `get_state_history(config)` and print the step number and `next` for each checkpoint. Identify which snapshot corresponds to which super-step.

## Further reading

- Persistence overview: https://docs.langchain.com/oss/python/langgraph/persistence
- Checkpointer libraries and setup: https://docs.langchain.com/oss/python/langgraph/persistence#checkpointer-libraries
- `get_state` / `get_state_history` and StateSnapshot: https://docs.langchain.com/oss/python/langgraph/persistence#get-state
- Postgres/SQLite savers on PyPI: `langgraph-checkpoint-postgres`, `langgraph-checkpoint-sqlite`
