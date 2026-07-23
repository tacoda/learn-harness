# 11 · Durable Execution & Time-Travel

## Mental model

Persistence (chapter 5) gave you a timeline of checkpoints per thread. This chapter is about *using* that timeline as more than a save file:

- **Durable execution** — a run survives failures. Because state is checkpointed at every super-step boundary, a crash mid-run leaves a valid checkpoint, and re-invoking with the same `thread_id` resumes from there instead of restarting. Work already done isn't redone.
- **Replay** — re-running from a past checkpoint. Point config at an earlier `checkpoint_id` and the graph re-executes forward from that point.
- **Time-travel** — inspecting, editing, and *forking* history. You can read any past checkpoint, overwrite its state, and branch a new timeline from it — the graph's version of "what if I'd answered differently three steps ago."

The unifying idea: the checkpoint history is an editable, branchable log. Durability, replay, and forking are three ways of reading and writing that log.

## In depth

### Durability guarantees

By default, running a graph with a checkpointer persists after every super-step. If the process dies between steps, the last completed step is safe. To resume, call the graph again with the same `thread_id` and `None` as input:

```python
config = {"configurable": {"thread_id": "job-7"}}
try:
    graph.invoke(inputs, config)
except SomeTransientError:
    ...  # process may even restart entirely
# Later, same thread: pick up from the last checkpoint.
graph.invoke(None, config)
```

The engine reads the last checkpoint, sees which nodes were queued (`get_state(config).next`), and continues. Nodes that already ran and committed their writes don't run again. (With the functional API, chapter 12, completed `@task` results are cached across a resume for the same reason.)

You can tune how aggressively state is persisted via the `durability` setting on invocation when you need to trade durability for throughput, but the default — persist every step — is the safe choice and what makes crash recovery automatic.

### Replaying from a checkpoint

Every checkpoint has a `checkpoint_id`, visible in `get_state_history` (chapter 5). Put one in config and invoking replays forward from that exact point:

```python
# Find a past checkpoint.
history = list(graph.get_state_history(config))
target = history[3]                      # some earlier StateSnapshot
replay_config = target.config            # carries thread_id + checkpoint_id

# Replay forward from there.
graph.invoke(None, replay_config)
```

If you replay from a checkpoint whose steps already ran, LangGraph *replays* (re-uses recorded results) rather than recomputing — replay is faithful, not a re-roll of randomness, unless you change something.

### Time-travel: editing and forking with `update_state`

The powerful move is to *change* the past and branch from it. `update_state` writes an update onto a checkpoint (applying reducers exactly as a node's return would) and produces a **new checkpoint** — a fork:

```python
# Take an earlier snapshot and overwrite part of its state.
fork_config = graph.update_state(
    target.config,                       # the checkpoint to fork from
    {"plan": "a different plan"},        # applied through the channel's reducer
)
# fork_config points at the new forked checkpoint. Run forward on the new branch:
graph.invoke(None, fork_config)
```

Now you have two branches sharing history up to `target` and diverging after it. This is how you implement "let the human edit the agent's plan and re-run from there," or explore alternative tool outputs, without losing the original timeline. You can also use `update_state` with an `as_node` argument to write the update *as if* a particular node produced it, which controls what runs next after the fork.

### Error recovery patterns

- **Transient failures** (network blip, rate limit): let the step fail, then re-invoke with `None` on the same thread — the completed prefix is preserved and you resume.
- **Bad model output**: fork at the checkpoint before the bad step with `update_state` to correct the input, then run forward on the new branch.
- **Human correction**: identical to time-travel — inspect history, `update_state` to inject the human's fix, resume. This is HITL (chapter 7) generalized to any past point, not just a live interrupt.

### Inspecting before you act

Always look before forking. `get_state_history` gives you the full list newest-first; each snapshot's `.metadata["step"]`, `.next`, and `.values` tell you what happened and what was about to happen. Pick your fork point deliberately — forking from the wrong checkpoint re-runs the wrong steps.

## Why it matters

Long-running and consequential agents *will* hit failures: a model times out, a tool 500s, a process gets recycled. Without durable execution, every failure means restarting from scratch — re-spending tokens and re-doing side effects. With it, recovery is a single re-invocation. Time-travel turns the same machinery into a debugging and product superpower: you can reproduce a bad run exactly, edit one decision, and see the counterfactual, or let users branch a conversation. These aren't exotic features bolted on — they're the checkpoint log viewed through different verbs, which is why they compose with persistence, HITL, and subgraphs without special cases.

## Pitfalls

- **Expecting durability without a checkpointer.** No checkpointer, no timeline, no resume. Durable execution requires one, and in production a persistent one (Postgres/SQLite).
- **Non-idempotent side effects on replay/resume.** Replaying or resuming may re-enter a node. If a node has external side effects (charge a card, send mail) not guarded by state, you can double them. Gate side effects on state or make them idempotent.
- **Forking from the wrong checkpoint.** `update_state` on the latest checkpoint just edits the present; to branch history you must target the specific earlier `checkpoint_id` from `get_state_history`.
- **Assuming `update_state` replaces state wholesale.** It applies through each channel's reducer, exactly like a node return. An `add_messages` channel appends; it doesn't overwrite. Account for the reducer.
- **Confusing replay with re-rolling.** Replay re-uses recorded results for already-executed steps; it doesn't re-sample the model unless you change the input at the fork.
- **Stale-tutorial trap.** Older tutorials treat crash recovery as a manual, application-level concern and don't mention `get_state_history` / `update_state` forking. In v1 these are first-class graph methods; time-travel is a documented feature, not a hack.

## Exercises

1. Run a multi-step graph, then simulate a crash by raising in the last node. Re-invoke with `None` on the same thread and confirm earlier steps didn't re-run.
2. Use `get_state_history` to grab an early checkpoint, `update_state` to change one field, and run forward. Confirm you now have two branches by inspecting history of both configs.
3. Demonstrate the reducer subtlety: `update_state` a `messages` channel and observe that it appends rather than replaces. Then do the same on a plain replace-reducer key.
4. Build a node with a side effect (append to an external list) and show it double-fires on a naive replay. Fix it by gating the side effect on state.

## Further reading

- Durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- Time-travel (replay & fork): https://docs.langchain.com/oss/python/langgraph/time-travel
- `update_state` and `get_state_history`: https://docs.langchain.com/oss/python/langgraph/persistence#update-state
- Persistence overview: https://docs.langchain.com/oss/python/langgraph/persistence
