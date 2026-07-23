# 01 · Chat Models & Messages

## Mental model

A chat model is a **function from a list of messages to a message**. Everything else in this track — prompts, tools, agents, retrieval — is scaffolding around that one call. `init_chat_model` gives you a provider-agnostic handle to that function so your code doesn't hard-code Anthropic or OpenAI. The model is a `Runnable`, so it speaks `.invoke` / `.stream` / `.batch` like every other composable piece you'll meet later.

## In depth

### Getting a model

`init_chat_model` resolves a string to a concrete provider integration and returns a configured `BaseChatModel`:

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("claude-sonnet-4-6")            # provider inferred
model = init_chat_model("anthropic:claude-sonnet-4-6")  # provider explicit
```

The `provider:model` form is the unambiguous one — use it in shared code. The provider integration (`langchain-anthropic`, `langchain-openai`, …) must be installed; if it isn't, the error names the package to add. Core stays provider-agnostic on purpose.

### Messages

A conversation is an ordered list of typed messages. The types you'll use:

| Type | Role | Purpose |
|---|---|---|
| `SystemMessage` | `system` | Standing instructions / persona |
| `HumanMessage` | `user` | Input from the user |
| `AIMessage` | `assistant` | Model output (may carry `tool_calls`) |
| `ToolMessage` | `tool` | Result of a tool call, keyed by `tool_call_id` |

```python
from langchain.messages import SystemMessage, HumanMessage

messages = [
    SystemMessage("You are a terse assistant. One sentence maximum."),
    HumanMessage("Why is the sky blue?"),
]
response = model.invoke(messages)
print(response.content)          # str for simple text replies
print(type(response))            # <class 'langchain_core.messages.ai.AIMessage'>
```

You can skip the message classes and pass **OpenAI-style dicts** or a bare string — the model normalizes them:

```python
model.invoke("Why is the sky blue?")
model.invoke([{"role": "user", "content": "Why is the sky blue?"}])
```

The dict form is what you'll see inside agents (`agent.invoke({"messages": [{"role": "user", "content": "..."}]})`). All three forms produce the same normalized message list.

### Multimodal content blocks

`content` is either a string *or* a list of **content blocks** — the structured form that carries images, files, and (on output) reasoning and citations. To send an image:

```python
from langchain.messages import HumanMessage

message = HumanMessage(content=[
    {"type": "text", "text": "Describe this image in one line."},
    {"type": "image", "source_type": "url", "url": "https://example.com/cat.png"},
])
model.invoke([message])
```

On the way out, read `response.content_blocks` for a normalized, provider-independent view (text, tool calls, reasoning, citations) rather than parsing raw `content` yourself. This is the v1-stable accessor — prefer it in new code.

### invoke / stream / batch

Because the model is a `Runnable`, it has three execution shapes plus async twins:

```python
model.invoke(messages)                      # one call, one AIMessage
for chunk in model.stream(messages):        # token-by-token AIMessageChunks
    print(chunk.text, end="", flush=True)
model.batch([messages_a, messages_b])       # concurrent, order preserved
await model.ainvoke(messages)               # async
```

`.batch` runs its inputs concurrently under the hood and returns results in input order — reach for it over a Python loop when you have many independent calls.

### Parameters

Set generation parameters at construction, or per-call with `.bind`:

```python
model = init_chat_model("claude-sonnet-4-6", temperature=0, max_tokens=1024)

creative = model.bind(temperature=0.9)   # returns a new Runnable; original unchanged
```

`temperature=0` for extraction, classification, and anything you'll evaluate for correctness; raise it only when you want variety. `.bind` is non-mutating — it returns a new configured Runnable, which is how you keep one base model and derive variants.

### Swapping providers

Because everything downstream depends only on the `BaseChatModel` interface, switching providers is a one-line change:

```python
model = init_chat_model("gpt-5-mini")       # was "claude-sonnet-4-6"
```

Your prompts, tools, and agent code don't change. `configurable_fields` / `config_alternatives` let you defer the choice all the way to invocation time if you want to A/B models.

## Why it matters

The provider-agnostic `BaseChatModel` interface is the whole reason LangChain exists. It buys you **substitution without rewrites**: swap models to chase price/latency/quality, run the same eval suite across providers, and avoid lock-in. The cost is a thin abstraction layer that occasionally lags a provider's newest bespoke feature — but content blocks and `.bind` cover the vast majority of what those features expose, and the portability is almost always worth it.

## Pitfalls

- **Assuming `.content` is always a string.** With multimodal or reasoning models it's a list of blocks. Use `.content_blocks` for a stable, typed view.
- **Copying `ChatOpenAI(...)` / `ChatAnthropic(...)` directly from old tutorials.** That still works, but `init_chat_model` is the v1 idiom and keeps provider choice out of your business logic.
- **`.stream` doesn't lower latency to first *result*.** It lowers latency to first *token*. Total tokens and cost are unchanged.
- **Forgetting the provider package.** `init_chat_model("claude-...")` throws until `langchain-anthropic` is installed.
- **Mutating expectations around `.bind`.** It returns a new Runnable; the original is untouched. Assign the result.

## Exercises

1. Print `ready` from `init_chat_model("claude-sonnet-4-6")`, then swap to another provider changing only the model string and confirm identical downstream code.
2. Send an image via a `HumanMessage` content-block list and read the description off `response.content_blocks`.
3. Build a 5-element `.batch` and compare wall-clock time against a `for` loop of `.invoke` calls.
4. Construct one base model at `temperature=0`, derive a `temperature=0.9` variant with `.bind`, and confirm the base is unchanged.

## Further reading

- Models: https://docs.langchain.com/oss/python/langchain/models
- Messages & content blocks: https://docs.langchain.com/oss/python/langchain/messages
- `init_chat_model` reference: https://docs.langchain.com/oss/python/langchain/models
