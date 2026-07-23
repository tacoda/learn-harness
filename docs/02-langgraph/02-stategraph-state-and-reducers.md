# 02 · StateGraph, State & Reducers

## Mental model

State is the whole game. In LangGraph there is exactly one state object per run, and every node interacts with the graph *only* by reading it and returning updates to it. Two questions define your state design:

1. **What keys exist?** Each top-level key of your state is an independent **channel**.
2. **How does each key merge updates?** Each channel has a **reducer** — a function `(current, update) -> new`. The default reducer is "replace." Annotate a key to choose a different one (e.g. append).

Once you internalize "a state key is a channel with a reducer," most surprising behaviour stops being surprising. A node returning `{"count": 5}` doesn't set count to 5 in general — it *sends 5 as an update to the count channel*, and the channel's reducer decides what that means. With the default reducer it overwrites; with `operator.add` it adds; with `add_messages` it appends-or-merges.

## In depth

### The default: replace

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    topic: str
    draft: str


def write(state: State) -> dict:
    return {"draft": f"A short note on {state['topic']}."}


builder = StateGraph(State)
builder.add_node("write", write)
builder.add_edge(START, "write")
builder.add_edge("write", END)
graph = builder.compile()

graph.invoke({"topic": "reducers", "draft": ""})
# -> {"topic": "reducers", "draft": "A short note on reducers."}
```

`topic` and `draft` use the implicit replace reducer: whatever a node returns for that key becomes the new value. A node that doesn't mention a key leaves it untouched.

### Annotated reducers

To change how a key merges, wrap its type in `Annotated[type, reducer]`:

```python
import operator
from typing import Annotated, TypedDict


class State(TypedDict):
    # Each update to `steps` is appended to the running list.
    steps: Annotated[list[str], operator.add]
    # Each update to `total` is added to the current value.
    total: Annotated[int, operator.add]
```

Now a node returning `{"steps": ["parsed"]}` appends `"parsed"` rather than replacing the list, and `{"total": 3}` adds 3 to whatever total already holds. This is the entire mechanism behind accumulation, and it's what makes parallel fan-in work: several nodes can each contribute to `steps` in one super-step, and the reducer combines all their contributions deterministically.

### `add_messages`: the reducer you'll use most

Conversation state needs more than append — messages have ids, and a re-emitted message with the same id should *update in place* rather than duplicate. That's `add_messages`:

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list, add_messages]
```

`add_messages` will: append new messages, merge (overwrite) any message whose id matches an existing one, coerce dict-shaped messages into LangChain message objects, and assign ids where missing. This is why streaming token updates and tool-message edits behave sanely — the reducer reconciles by id instead of blindly appending.

### Custom reducers

A reducer is any pure function `(left, right) -> merged`. Write your own when neither replace, add, nor `add_messages` fits:

```python
from typing import Annotated, TypedDict


def merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}


class State(TypedDict):
    scratch: Annotated[dict, merge_dicts]
```

Now `{"scratch": {"a": 1}}` from one node and `{"scratch": {"b": 2}}` from another combine to `{"a": 1, "b": 2}` instead of the second clobbering the first. Keep reducers **pure and commutative-friendly**: in a parallel super-step you cannot rely on which update arrives "first," so a reducer whose result depends on ordering will give you nondeterministic bugs.

### Multiple keys and separation of concerns

Real graphs have several keys with different lifetimes: `messages` (the conversation), `plan` (a working artifact), `iteration` (a counter), `results` (accumulated output). Give each the reducer that matches how it evolves. Don't cram everything into `messages` — that's context you're forced to send to the model whether it's relevant or not.

### Input, output, and private schemas

By default the state schema is also the input and output schema. You can narrow each end so callers see a clean contract while the graph keeps internal scratch state:

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


class InputState(TypedDict):
    question: str


class OutputState(TypedDict):
    answer: str


class OverallState(TypedDict):
    question: str
    answer: str
    scratch: str  # internal, not exposed to callers


def solve(state: OverallState) -> dict:
    return {"scratch": "thinking...", "answer": f"Re: {state['question']}"}


builder = StateGraph(OverallState, input_schema=InputState, output_schema=OutputState)
builder.add_node("solve", solve)
builder.add_edge(START, "solve")
builder.add_edge("solve", END)
graph = builder.compile()

graph.invoke({"question": "why?"})  # -> {"answer": "Re: why?"} ; scratch is hidden
```

`input_schema` filters what `invoke` accepts, `output_schema` filters what it returns, and any key present only in the overall schema is **private** — usable between nodes but never surfaced. This is the clean way to keep working state out of your public interface. You can also give individual nodes their own private input/output type annotations to declare that a node only reads or writes a subset of state.

## Why it matters

State design is where expert LangGraph time goes. The reducer you pick determines whether parallel nodes compose or corrupt each other, whether your conversation grows correctly, and whether your public API stays clean. Get the schema right and control flow becomes easy; get it wrong and you'll fight mysterious "my update disappeared" bugs that are really two writers racing on a replace-reducer channel. Well-chosen private/input/output schemas also keep the model's context small, which is the single biggest lever on cost and quality.

## Pitfalls

- **Forgetting a reducer on a key two nodes write in parallel.** With the default replace reducer, one write silently wins. Add `operator.add` or a custom merge so both contributions survive.
- **Order-dependent reducers.** A parallel super-step has no internal ordering. If your reducer's output depends on which update came first, you have a nondeterminism bug.
- **Overloading `messages`.** Stuffing plans, scratch notes, and results into the message list forces all of it into the model's context. Use separate keys.
- **Returning the whole state from a node.** Nodes return *partial* updates. Returning a full state dict (especially re-returning `messages` you didn't change) can re-trigger reducers unexpectedly.
- **Stale-tutorial trap.** Old material uses `MessageGraph` or a bare `messages` list without `add_messages`, and imports `add_messages` from moved locations. In v1 it's `from langgraph.graph.message import add_messages`, and typed `TypedDict` state is the norm.

## Exercises

1. Build a state with `steps: Annotated[list, operator.add]`. Add two nodes that each append one step and run them in parallel (fan-out from `START` to both, fan-in to `END`). Confirm both steps appear regardless of run.
2. Write a custom reducer `keep_max(left, right)` for an `int` channel that keeps the larger value. Prove it's order-independent by feeding updates in both orders.
3. Split a graph into `input_schema`, `output_schema`, and an overall schema with one private scratch key. Verify the scratch key never appears in `invoke`'s return value.
4. Replace `add_messages` with plain replace on a `messages` key and observe what happens to conversation history across two nodes. Explain the difference in one sentence.

## Further reading

- Graph API — state, reducers, schemas: https://docs.langchain.com/oss/python/langgraph/graph-api
- `add_messages` and message state: https://docs.langchain.com/oss/python/langgraph/graph-api#messagesstate
- Low-level concepts (channels & reducers): https://docs.langchain.com/oss/python/langgraph/pregel
