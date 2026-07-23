# 12 · The Functional API

## Mental model

Everything so far has used the **graph API**: you declare nodes and edges, and the engine walks the graph. The **functional API** is a second way to write the same runtime, in ordinary Python control flow. Instead of building a `StateGraph`, you write a normal function and decorate it:

- **`@entrypoint`** marks a function as a durable workflow. Its body uses regular Python — `if`, `for`, `while`, function calls — and LangGraph wraps it with persistence, streaming, interrupts, and resumption.
- **`@task`** marks a unit of work called from within an entrypoint. Tasks return futures, so they can run in parallel, and their results are checkpointed — on resume, completed tasks are *not* re-run.

The trade: the graph API makes structure explicit and visualizable (you can draw it); the functional API makes structure *implicit* in your code (you read it like a normal program). Same engine, same durability guarantees, same checkpointers, same `interrupt`. You're choosing an authoring style, not a different runtime.

## In depth

### A minimal entrypoint

```python
from langgraph.func import entrypoint, task


@task
def add_one_task(a: int) -> int:
    return a + 1


@entrypoint()
def add_one(numbers: list[int]) -> list[int]:
    futures = [add_one_task(n) for n in numbers]   # each call returns a future
    return [f.result() for f in futures]           # .result() awaits


add_one.invoke([1, 2, 3])   # -> [2, 3, 4]
```

Calling a `@task` returns a future immediately; the work runs concurrently, and `.result()` blocks for its value. So the list comprehension above fans out all the increments in parallel and then joins — the functional-API equivalent of a graph fan-out/fan-in, expressed as plain Python.

### Sequential composition is just calling `.result()`

```python
@task
def foo(x: str) -> str: return x + "|foo"

@task
def bar(x: str) -> str: return x + "|bar"


@entrypoint()
def workflow(inp: str) -> str:
    a = foo(inp).result()    # wait for foo before bar
    b = bar(a).result()
    return b
```

Chaining `.result()` sequences tasks; not chaining them lets them run in parallel. Control flow — branches, loops, early returns — is just Python, which is the whole point: complex conditional logic that would be several conditional edges in the graph API is an `if` statement here.

### Durability: the entrypoint needs a checkpointer

Pass a checkpointer to `@entrypoint(...)` and the workflow becomes durable exactly like a compiled graph. Completed `@task` results are cached in the checkpoint, so a resume skips re-executing them:

```python
from langgraph.checkpoint.memory import InMemorySaver


@entrypoint(checkpointer=InMemorySaver())
def workflow(inp: str) -> dict:
    result = slow_task(inp).result()   # on resume, not recomputed if already done
    return {"result": result}


config = {"configurable": {"thread_id": "1"}}
workflow.invoke("x", config)
```

This is the same super-step-boundary checkpointing as the graph API — the checkpointer records task results at the boundaries and replays them rather than recomputing on resume.

### Human-in-the-loop works identically

`interrupt` (chapter 7) works inside an entrypoint just as it does inside a node. Pause, surface a payload, resume with `Command(resume=...)`:

```python
from langgraph.types import interrupt, Command


@entrypoint(checkpointer=InMemorySaver())
def review_workflow(topic: str) -> dict:
    essay = compose_essay(topic).result()
    human_review = interrupt({"question": "Please review", "essay": essay})
    return {"essay": essay, "review": human_review}


config = {"configurable": {"thread_id": "t1"}}
for chunk in review_workflow.stream(topic, config):   # runs until interrupt
    print(chunk)
review_workflow.invoke(Command(resume="looks good"), config)   # resumes
```

The same re-run caveat applies: on resume the entrypoint body re-executes from the top, but completed tasks are cached (not re-run), which neatly avoids the "side effect fires twice" problem *for work you put in tasks*. Keep raw side effects inside `@task`s so they're checkpointed and not repeated.

### When to prefer the functional API

- **Complex, dynamic control flow** that's awkward as a static graph — deeply nested conditionals, loops whose structure depends on data, logic you'd rather read as a program than a diagram.
- **Porting existing code** — you have a working Python function and want durability, streaming, and HITL without restructuring it into nodes and edges.
- **Small workflows** where drawing a graph is overkill.

Prefer the **graph API** when structure is the point: when you want a visualizable topology, when multiple agents share and reduce state, when the control flow *is* the design (branches, parallel fan-out, multi-agent handoffs) and you benefit from seeing it laid out. Many real systems mix both — an entrypoint that calls into compiled graphs, or a graph node that wraps functional logic.

## Why it matters

The functional API lowers the cost of adopting LangGraph's runtime. You don't have to translate your program into a graph to get durability and resumption — you decorate what you already have. For workflows dominated by conditional logic, it's genuinely more readable than a spray of conditional edges. But it hides structure, which is exactly what you *want* visible in a multi-agent or heavily-parallel system. Knowing both, and that they're the same engine, lets you pick the authoring style that makes each particular workflow easiest to change — which is the whole objective.

## Pitfalls

- **Expecting durability without a checkpointer on the entrypoint.** `@entrypoint()` with no checkpointer runs but doesn't persist or resume. Pass one for durable/HITL workflows.
- **Side effects in the entrypoint body instead of in a `@task`.** The body re-runs on resume; only `@task` results are cached. Put anything that must run exactly once inside a task.
- **Forgetting `.result()`.** A `@task` call returns a future, not a value. Using it directly (without `.result()`) gives you a future where you expected data.
- **Assuming no parallelism.** Multiple `@task` calls before their `.result()` run concurrently. If you need strict ordering, chain `.result()` deliberately.
- **Reaching for it when structure matters.** For multi-agent topologies and heavy fan-out you want the graph API's explicit, visualizable shape; the functional API hides it.
- **Stale-tutorial trap.** The functional API is a v1-era addition; older tutorials only show `StateGraph`. Also verify imports — it's `from langgraph.func import entrypoint, task`.

## Exercises

1. Rewrite a small conditional graph (a branch and a join) as an `@entrypoint` with `@task`s. Compare readability against the graph version.
2. Add a checkpointer to an entrypoint, put a slow `@task` in it, interrupt after it, and resume. Confirm the slow task is *not* recomputed on resume.
3. Show parallelism: call three `@task`s without immediately resolving them, then resolve all three. Measure that total time is roughly one task's time, not three.
4. Put a side effect (append to a file) once in the entrypoint body and once in a `@task`, trigger a resume via `interrupt`, and observe which one double-fires. Explain why.

## Further reading

- Functional API guide: https://docs.langchain.com/oss/python/langgraph/functional-api
- `@entrypoint` and `@task` reference: https://docs.langchain.com/oss/python/langgraph/functional-api#entrypoint
- Functional API + human-in-the-loop: https://docs.langchain.com/oss/python/langgraph/functional-api#human-in-the-loop
- Durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
