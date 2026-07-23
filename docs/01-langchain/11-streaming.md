# 11 · Streaming

## Mental model

Streaming is about **what** you emit incrementally, not just *that* you emit. Every Runnable streams, but "streaming" means different things at different granularities: **tokens** (the model's text as it's generated), **steps** (each node of the agent loop as it completes), and **events** (a fine-grained firehose of every start/end inside the whole run). You pick the granularity with `stream_mode`. Matching the mode to your UI need — a typing effect, a "calling tool…" indicator, or a debug trace — is the whole skill.

## In depth

### `.stream` vs. `.astream`

Sync and async twins. Use `.astream` in async apps so streaming doesn't block the event loop; otherwise identical semantics:

```python
for chunk in agent.stream(inputs, stream_mode="messages"): ...
async for chunk in agent.astream(inputs, stream_mode="messages"): ...
```

### `stream_mode`: the four granularities

| `stream_mode` | Emits | Use for |
|---|---|---|
| `"messages"` | LLM tokens as `(chunk, metadata)` | Typing effect / live text |
| `"updates"` | State delta after each node (model, tools) | "Calling get_weather…" step UI |
| `"values"` | The **full** state after each step | Debugging, snapshots |
| `"custom"` | Arbitrary data your tools emit | Progress from inside a tool |

### Streaming tokens

`stream_mode="messages"` streams the model's output token-by-token. Each chunk is `(token, metadata)`; read `token.content_blocks` (the stable, typed view) and `metadata["langgraph_node"]` to know which node produced it:

```python
from langchain.agents import create_agent

agent = create_agent(model="claude-sonnet-4-6", tools=[get_weather])

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "Weather in SF?"}]},
    stream_mode="messages",
    version="v2",
):
    if chunk["type"] == "messages":
        token, metadata = chunk["data"]
        print(f"[{metadata['langgraph_node']}] {token.content_blocks}")
```

Pass `version="v2"` — it's the current event schema for agent streaming.

### Streaming steps

`stream_mode="updates"` emits once per completed node — ideal for a UI that shows *what the agent is doing* rather than the raw tokens:

```python
for chunk in agent.stream(inputs, stream_mode="updates", version="v2"):
    if chunk["type"] == "updates":
        for node, update in chunk["data"].items():
            if node in ("model", "tools"):
                print(f"step: {node} -> {update['messages'][-1]}")
```

### Multiple modes at once

Pass a list to get several streams interleaved; disambiguate on `chunk["type"]`. This is the production pattern — tokens for the text, updates for the step indicators:

```python
for chunk in agent.stream(
    inputs,
    stream_mode=["messages", "updates"],
    version="v2",
):
    if chunk["type"] == "messages":
        token, meta = chunk["data"]
        ...   # render tokens
    elif chunk["type"] == "updates":
        for node, update in chunk["data"].items():
            ...   # render step
```

Add `subgraphs=True` when your agent spawns sub-agents and you want their internal steps too (each chunk then carries a namespace `ns` telling you which subgraph it came from).

### Custom data from tools

A long-running tool can push progress into the `"custom"` stream via the config writer, so the UI shows "downloading… processing…" mid-tool:

```python
from langchain.tools import tool, ToolRuntime

@tool
def crunch(dataset: str, runtime: ToolRuntime) -> str:
    """Process a dataset."""
    runtime.stream_writer(f"loading {dataset}")   # -> appears in stream_mode="custom"
    result = process(dataset)
    runtime.stream_writer("done")
    return result
```

### `astream_events`: the firehose

For deep observability — every model start/stop, tool start/stop, chain step, token — use `astream_events` (async only, `version="v2"`). It emits a typed event per lifecycle boundary of every nested Runnable:

```python
async for event in agent.astream_events(inputs, version="v2"):
    kind = event["event"]          # e.g. "on_chat_model_stream", "on_tool_end"
    if kind == "on_chat_model_stream":
        print(event["data"]["chunk"].content_blocks, end="")
    elif kind == "on_tool_end":
        print(f"\ntool {event['name']} -> {event['data']['output']}")
```

Use `astream_events` when you're building custom observability or a rich UI that needs every boundary; use `stream_mode` for ordinary token/step streaming. `astream_events` is heavier — it's the diagnostic tool, not the default.

## Why it matters

Streaming is a **UX and latency** decision, and the granularity choice is the crux. Token streaming cuts perceived latency (users see output immediately) but says nothing about *what the agent is doing between messages*; step streaming narrates the loop but not the text; events give you everything at the cost of volume. Picking the wrong granularity means either a UI that stalls silently during a two-minute tool call, or a firehose you have to filter down to nothing. The design payoff is that all of it rides the same `.stream`/`.astream` interface every Runnable already has — you opt into detail, you don't wire up a separate mechanism.

## Pitfalls

- **Omitting `version="v2"`.** Agent streaming expects the v2 schema; without it you get the older event shape and mismatched chunk fields.
- **Streaming tokens but rendering nothing during tool calls.** Token mode is silent while a tool runs. Combine `["messages", "updates"]` so the UI shows step progress too.
- **`astream_events` as the default.** It's the heavy diagnostic firehose. For a typing effect, `stream_mode="messages"` is far cheaper.
- **Parsing raw `content` from chunks.** Use `token.content_blocks` — the stable typed accessor — not string-slicing `content`, which varies by provider and modality.
- **A non-streaming final stage.** If your chain ends in a component that buffers (some parsers/aggregations), `.stream` yields one chunk at the end. Streaming reflects the *last* stage's behavior.
- **Sync `.stream` in async code.** Blocks the event loop. Use `.astream` / `astream_events`.
- **Forgetting `subgraphs=True` for multi-agent.** Without it, a sub-agent's internal steps don't surface and the UI looks frozen during delegation.

## Exercises

1. Stream an agent with `stream_mode="messages"` and render a live typing effect from `token.content_blocks`.
2. Switch to `"updates"` and print a human-readable "calling <tool>…" line per step.
3. Combine `["messages", "updates"]` and drive both a text pane and a step indicator from one stream.
4. Add a tool that emits custom progress via `stream_writer` and surface it with `stream_mode="custom"`.
5. Use `astream_events(version="v2")` to log every `on_tool_start` / `on_tool_end` with arguments and results.

## Further reading

- Streaming: https://docs.langchain.com/oss/python/langchain/streaming
- `astream_events` reference: https://docs.langchain.com/oss/python/langchain/streaming
- Runnables (streaming semantics): https://docs.langchain.com/oss/python/langchain/runnables
