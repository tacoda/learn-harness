# 08 · Streaming

## Mental model

A graph run is not one event — it's a sequence: nodes fire, state changes, the model emits tokens. Streaming lets you observe that sequence *as it happens* instead of waiting for the final result. The question streaming answers is "what do you want to watch?", and LangGraph gives you several lenses via `stream_mode`:

- **`"values"`** — the *full state* after each super-step. Good for "show me the whole state as it evolves."
- **`"updates"`** — only the *delta each node returned*, keyed by node name. Good for "which node just did what."
- **`"messages"`** — LLM *tokens* as they generate, for streaming a chat response to a UI.
- **`"custom"`** — arbitrary data your nodes emit deliberately (progress, intermediate artifacts).
- **`"debug"`** — verbose engine events (tasks, checkpoints) for tracing and diagnosis.

You call `graph.stream(input, config, stream_mode=...)` and iterate the results. Pick the mode by what your consumer needs: a UI chat bubble wants `"messages"`; a progress log wants `"updates"`; a debugger wants `"debug"`.

## In depth

### `values` vs. `updates`

```python
for chunk in graph.stream({"messages": [{"role": "user", "content": "hi"}]},
                          config, stream_mode="values"):
    print(chunk["messages"][-1])   # full state each step: the list keeps growing

for chunk in graph.stream({"messages": [{"role": "user", "content": "hi"}]},
                          config, stream_mode="updates"):
    print(chunk)   # {node_name: {partial update that node returned}}
```

`values` gives you the complete state repeatedly (each emission is the whole thing after a super-step); `updates` gives you just what changed and who changed it. For a fan-out super-step, `updates` shows one entry per node that ran.

### Streaming tokens with `messages`

```python
for token, metadata in graph.stream(inputs, config, stream_mode="messages"):
    print(token.content, end="", flush=True)   # token is a message chunk
    # metadata tells you which node / model produced it
```

`"messages"` emits `(message_chunk, metadata)` tuples as the model generates. This is how you get the typewriter effect in a chat UI. The metadata lets you attribute tokens to a node — essential when multiple model calls stream in one graph and you only want to surface one of them.

### Multiple modes at once

Pass a list and each emission is tagged with its mode, so you can multiplex:

```python
for mode, chunk in graph.stream(inputs, config, stream_mode=["updates", "messages"]):
    if mode == "messages":
        token, meta = chunk
        ...
    elif mode == "updates":
        ...
```

When you pass a list, each yielded item becomes a `(mode, chunk)` tuple so you can dispatch. This is the norm for a real app: stream tokens *and* watch node progress in one pass.

### Custom data from a node

Sometimes you want to stream something that isn't state or tokens — a progress percentage, a retrieved document, a status line. Emit it with the stream writer and read it via `stream_mode="custom"`:

```python
from langgraph.config import get_stream_writer


def long_step(state: State) -> dict:
    writer = get_stream_writer()
    writer({"progress": "fetching..."})
    # ...work...
    writer({"progress": "done"})
    return {"result": "..."}


for chunk in graph.stream(inputs, config, stream_mode="custom"):
    print(chunk)   # {"progress": "fetching..."} then {"progress": "done"}
```

`get_stream_writer()` gives the running node a channel to push arbitrary payloads into the `"custom"` stream, independent of state. Use it for anything you want the UI to see that doesn't belong in state.

### Async streaming

Everything above has an async twin: `astream` with the same `stream_mode` values, driven with `async for`. Use it when your app is async (a web server handling concurrent requests):

```python
async for chunk in graph.astream(inputs, config, stream_mode="messages"):
    ...
```

Pair `astream` with an async checkpointer (`AsyncPostgresSaver`, `AsyncSqliteSaver`) so the whole path is non-blocking.

### Streaming through subgraphs

By default a stream shows the parent graph's activity. To also surface events from nested subgraphs (chapter 9), pass `subgraphs=True`; emissions then include a namespace path identifying which subgraph produced them.

## Why it matters

Latency is the enemy of agent UX. A model that takes eight seconds to answer feels broken if the user stares at a blank screen; the same eight seconds feel fast when tokens stream in immediately. Streaming is also how you build observability into the request path — `updates` and `debug` tell you what the graph is doing *while* it does it, which is often faster than reading traces after the fact. Choosing the right mode (and combining modes) is the difference between a responsive product and one that appears to hang.

## Pitfalls

- **Using `values` when you want deltas.** `values` re-emits the entire state each step, which is wasteful and confusing if you only care about what changed. Use `updates`.
- **Expecting `messages` tokens without a streaming-capable model.** The mode surfaces tokens only if the underlying model streams; a non-streaming model yields whole messages.
- **Ignoring the metadata in `messages` mode.** With multiple model calls in one graph, you'll interleave tokens from different nodes unless you filter on the metadata.
- **Forgetting `subgraphs=True`.** If your work happens inside a subgraph and you don't see its events, you likely need to opt into subgraph streaming.
- **Mixing sync `stream` with an async app.** Use `astream` (and an async saver) in async contexts to avoid blocking the event loop.
- **Stale-tutorial trap.** Older material streams via LangChain callback handlers or `astream_events` on chains. In LangGraph v1, `graph.stream(..., stream_mode=...)` is the native surface; `get_stream_writer()` (for custom data) replaces older callback hacks.

## Exercises

1. Run the same graph three times with `stream_mode` set to `"values"`, `"updates"`, and `"messages"`. Describe in one line what each stream is showing you.
2. Stream with `stream_mode=["updates", "messages"]` and write a loop that prints node-progress lines and token text differently based on the mode tag.
3. Add `get_stream_writer()` calls to a slow node emitting progress, and consume them with `stream_mode="custom"`. Confirm the progress appears before the node's final result.
4. Convert a streaming loop to `astream` inside an `async def`, pair it with an async checkpointer, and confirm token streaming still works.

## Further reading

- Streaming overview and modes: https://docs.langchain.com/oss/python/langgraph/streaming
- Streaming LLM tokens (`messages`): https://docs.langchain.com/oss/python/langgraph/streaming#messages
- Custom streaming with `get_stream_writer`: https://docs.langchain.com/oss/python/langgraph/streaming#custom
- Streaming from subgraphs: https://docs.langchain.com/oss/python/langgraph/streaming#subgraphs
