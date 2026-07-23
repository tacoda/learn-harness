# 07 · Human-in-the-Loop & Interrupts

## Mental model

Some steps shouldn't happen without a human: sending an email, spending money, deleting data, committing to a plan. Human-in-the-loop (HITL) means the graph can **pause mid-run, surface something to a person, and resume with their input** — possibly minutes or days later.

The mechanism is a direct consequence of persistence. Because state is checkpointed at every super-step boundary (chapter 5), the engine can stop at a checkpoint, hand control back to your application, and later pick up exactly where it left off. So the one hard requirement is: **HITL requires a checkpointer.** No checkpointer, nowhere to pause.

The primitive is `interrupt(payload)`, called from *inside a node*. It:

1. Stops the graph and surfaces `payload` to the caller.
2. On the next invocation with `Command(resume=value)`, returns `value` from that same `interrupt(...)` call and the node continues.

Think of `interrupt` as a blocking `input()` that survives process restarts.

## In depth

### The basic pause/resume cycle

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver


def approval_node(state: State) -> dict:
    decision = interrupt({"action": "send_email", "to": state["recipient"]})
    if decision == "approve":
        return {"status": "sent"}
    return {"status": "cancelled"}


graph = builder.compile(checkpointer=InMemorySaver())  # checkpointer is mandatory
config = {"configurable": {"thread_id": "1"}}

# First call runs until interrupt(), then stops.
result = graph.invoke({"recipient": "ian@example.com"}, config)
print(result["__interrupt__"])   # the payload you passed to interrupt()

# ...surface it to a human, collect their answer, then resume:
final = graph.invoke(Command(resume="approve"), config)
print(final["status"])           # "sent"
```

Two invocations, one logical run. The first returns when `interrupt` fires; its result contains the interrupt payload. The second passes `Command(resume=...)`, and execution re-enters `approval_node` — the `interrupt(...)` call now *returns* the resume value and the node runs to completion. The `thread_id` ties the two calls together via the checkpoint.

### A subtlety worth internalizing: the node re-runs

When you resume, the node containing `interrupt` runs **from the top again**, with the `interrupt(...)` expression now yielding the resume value instead of pausing. Any code *before* the `interrupt` executes a second time. So keep pre-interrupt code side-effect-free, or move side effects after the interrupt. This trips people up constantly: don't send the email before the approval `interrupt` "just to prepare it" — the resume will send it twice.

### The three common patterns

**Approve / reject** — gate an action:

```python
def guard(state: State):
    ok = interrupt({"review": state["proposed_action"]})
    return Command(goto="execute" if ok else "abort")
```

**Edit state** — let the human correct the agent before it proceeds:

```python
def review_plan(state: State):
    edited = interrupt({"plan": state["plan"]})   # human returns a revised plan
    return {"plan": edited}
```

**Review / provide input** — collect information the agent lacks (a missing field, a clarification). Same shape: `interrupt` a question, resume with the answer.

All three are the same primitive; only the payload and what you do with the resume value differ.

### Dynamic vs. static interrupts

`interrupt()` inside a node is a **dynamic interrupt**: it fires conditionally, wherever you put it, based on runtime state. This is the recommended, flexible approach.

There is also a **static** form set at compile time — pause *before* or *after* named nodes:

```python
graph = builder.compile(
    checkpointer=InMemorySaver(),
    interrupt_before=["execute"],   # pause before running "execute"
    interrupt_after=["plan"],       # pause after "plan" completes
)
```

Static interrupts are handy for debugging and for fixed approval gates you know at build time — the graph stops at the boundary and you resume with `invoke(None, config)` (no resume value needed, since nothing is waiting on one). Prefer dynamic `interrupt()` when the pause is conditional or needs to carry a payload; use static `interrupt_before/after` for unconditional, position-based stops.

### Inspecting a paused graph

When a graph is paused, `get_state(config).next` is non-empty (it names the node about to run) and `get_state(config).tasks` surfaces the pending interrupt and its payload. That's how a server-side application knows a thread is waiting on a human and what to ask them.

## Why it matters

HITL is what makes agents deployable for consequential work. Nobody lets an unattended model send customer emails or move money; a pause-for-approval gate is the price of shipping. Because it's built on checkpointing, the pause is *durable* — the human can respond hours later from a different process, and the run resumes intact. That's categorically different from a blocking prompt in a script. Getting the re-run semantics right (side effects after the interrupt, not before) is the one piece of expertise that separates a HITL agent that works from one that double-sends.

## Pitfalls

- **No checkpointer.** `interrupt` without a checkpointer has nowhere to persist the pause and will error. HITL always needs one.
- **Side effects before `interrupt`.** The node re-runs on resume, so any pre-interrupt side effect happens twice. Put side effects after the interrupt, or make them idempotent.
- **Forgetting to resume with `Command(resume=...)`.** Calling `invoke(inputs, config)` again with fresh inputs (instead of `Command(resume=value)`) doesn't answer the interrupt — it starts confused. Resume with a `Command`.
- **Reading the resume value from the wrong place.** The resume value is what `interrupt(...)` *returns*, not something in state. Capture it from the call.
- **Assuming static `interrupt_before` carries a payload.** It doesn't — it just stops at a boundary. If you need to hand the human structured data, use dynamic `interrupt(payload)`.
- **Stale-tutorial trap.** Older HITL tutorials rely solely on `interrupt_before` at compile time (the dynamic `interrupt()` primitive is newer) or import `interrupt`/`Command` from moved paths. In v1 it's `from langgraph.types import interrupt, Command`, and dynamic `interrupt()` is the primary pattern.

## Exercises

1. Build an approve/reject gate with dynamic `interrupt()`. Run it, print the interrupt payload, then resume with both `"approve"` and (fresh thread) `"reject"` and confirm the two paths.
2. Put a `print("preparing")` *before* the `interrupt` and observe it fire twice across pause and resume. Move the side effect after the interrupt and confirm it fires once.
3. Implement the edit-state pattern: interrupt with a draft plan, resume with an edited plan, and confirm the graph continues with the human's version.
4. Compile a graph with `interrupt_before=["execute"]`, run to the pause, inspect `get_state(config).next` and `.tasks`, then resume with `invoke(None, config)`.

## Further reading

- Human-in-the-loop concepts: https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop
- `interrupt` and `Command(resume=...)`: https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop#interrupt
- Static interrupts (`interrupt_before` / `interrupt_after`): https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop#static-interrupts
- Persistence (why HITL needs a checkpointer): https://docs.langchain.com/oss/python/langgraph/persistence
