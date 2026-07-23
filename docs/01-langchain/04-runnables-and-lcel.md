# 04 · Runnables & LCEL

## Mental model

**Everything composable in LangChain is a `Runnable`.** A model, a prompt, a retriever, an output parser, a tool, a chain, even a plain function you wrap — all expose the same interface: `.invoke`, `.stream`, `.batch`, and their async twins. Because they share one interface, you can wire them together with a single operator, `|`. That is LCEL (LangChain Expression Language): pipe left-to-right, each stage's output becomes the next stage's input. Learn this one abstraction and the rest of the library stops being a pile of classes and becomes a set of interchangeable parts.

## In depth

### The Runnable interface

Every Runnable answers the same calls:

```python
r.invoke(x)          # run once, return the result
r.stream(x)          # yield incremental chunks
r.batch([x1, x2])    # run many inputs concurrently, results in order
await r.ainvoke(x)   # async single
async for c in r.astream(x): ...   # async streaming
```

You get all six for free the moment something is a Runnable. This uniformity is the payoff — you never learn a bespoke API per component.

### Composition with `|`

The pipe builds a `RunnableSequence`. Output of the left feeds the right:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.chat_models import init_chat_model

prompt = ChatPromptTemplate.from_messages([("user", "Explain {topic} in one sentence.")])
model = init_chat_model("claude-sonnet-4-6")

chain = prompt | model | StrOutputParser()
chain.invoke({"topic": "entropy"})     # -> a plain string
```

The composed `chain` is itself a Runnable — it has `.stream`, `.batch`, `.ainvoke` too. Streaming a sequence streams the *last* stage: `chain.stream({...})` yields string tokens because `StrOutputParser` streams.

### The primitives: Parallel, Passthrough, Lambda

Three building blocks cover most non-linear wiring:

```python
from langchain_core.runnables import (
    RunnableParallel, RunnablePassthrough, RunnableLambda,
)

# RunnableParallel: fan one input out to several Runnables, collect a dict
mapping = RunnableParallel(
    joke=prompt_joke | model,
    fact=prompt_fact | model,
)   # {"joke": ..., "fact": ...} — branches run concurrently

# RunnablePassthrough: forward input unchanged, or attach computed keys
enrich = RunnablePassthrough.assign(
    length=RunnableLambda(lambda d: len(d["text"])),
)   # {"text": ..., "length": ...}

# RunnableLambda: lift any plain function into a Runnable
upper = RunnableLambda(lambda s: s.upper())
```

A **dict literal** in a pipe is coerced to `RunnableParallel`, and a **bare function** is coerced to `RunnableLambda` — so the common RAG shape reads naturally:

```python
chain = (
    {"context": retriever, "question": RunnablePassthrough()}   # -> RunnableParallel
    | prompt
    | model
    | StrOutputParser()
)
chain.invoke("What is LCEL?")
```

The retriever (a Runnable) fetches docs for `context` while the question passes through untouched, both feed the prompt. This is the canonical "retrieval chain" and it's nothing but Runnables piped together.

### Config: tags, metadata, and control

Every `.invoke` accepts a `RunnableConfig` — the sideband that carries tags, metadata, callbacks, concurrency limits, and `configurable` overrides through the whole chain:

```python
from langchain_core.runnables import RunnableConfig

config: RunnableConfig = {
    "tags": ["prod", "rag"],
    "metadata": {"user_id": "u_42"},
    "max_concurrency": 4,
    "run_name": "answer_question",
}
chain.invoke("What is LCEL?", config=config)
```

Config propagates automatically to every nested Runnable, which is how tags/metadata show up on each step in LangSmith without threading arguments by hand.

### Resilience: retry and fallbacks

Two decorators harden any Runnable:

```python
robust = model.with_retry(stop_after_attempt=3)          # retry transient failures
resilient = model.with_fallbacks([backup_model])          # switch on failure
```

`.with_retry` handles blips (rate limits, timeouts); `.with_fallbacks` swaps to an alternate Runnable when the primary raises. Both return new Runnables and compose in a pipe like anything else. Layer them: a primary-with-retry, falling back to a cheaper model.

### Sync and async

Every Runnable has async methods. In an async app, use `ainvoke` / `astream` / `abatch` end-to-end so nothing blocks the event loop. If a stage only implements sync, LangChain runs it in a thread pool — correct, but you lose true concurrency, so prefer async-native components on hot paths.

### How this connects to agents and LangGraph

`create_agent` returns a compiled LangGraph graph — which is itself a Runnable (`agent.invoke`, `agent.stream`). Inside that graph, **each node is fed a Runnable**: the model node calls your `BaseChatModel`, the tool node calls your tools. So the Runnable interface is the contract at *every* layer: the pieces you pipe with `|`, the agent as a whole, and the nodes of the graph underneath it all speak the same six methods. When you later drop to `StateGraph`, you're wiring Runnables into nodes by hand instead of letting `|` do it linearly.

## Why it matters

One interface for every component is the design decision that makes the ecosystem cohere. It means: uniform streaming and batching everywhere, composition without glue code, resilience you bolt on with a method call, and observability that threads through automatically via config. The tradeoff is a learning cliff — LCEL's coercion rules (dict→parallel, function→lambda) are implicit and can read as magic until they click. Once they do, you stop writing orchestration code and start declaring data flow.

## Pitfalls

- **Streaming the wrong stage.** `.stream` on a sequence streams the final Runnable. A non-streaming final stage (some parsers, aggregations) buffers the whole thing — you get one chunk.
- **Blocking the event loop.** Calling sync `.invoke` inside async code stalls it. Use `ainvoke`/`astream`.
- **Forgetting config propagates automatically.** Don't manually re-pass callbacks/tags into nested Runnables — set them once on the top-level `.invoke`.
- **Overusing `RunnableLambda` for side effects.** Lambdas should transform data; hiding I/O or mutation in them makes chains hard to trace and test.
- **`LLMChain` / `SequentialChain` nostalgia.** Those 0.x classes are gone. `prompt | model | parser` replaces all of them and is strictly more flexible.
- **Assuming `.batch` is parallel across processes.** It's concurrent within one process (threads/async), governed by `max_concurrency`. It is not distributed execution.

## Exercises

1. Build `prompt | model | StrOutputParser()` and confirm the composed object also supports `.stream` and `.batch`.
2. Rewrite a two-branch computation with `RunnableParallel` and verify the branches run concurrently (time it).
3. Construct the canonical RAG chain shape using a dict literal and `RunnablePassthrough()`; identify where the implicit coercions happened.
4. Wrap a model with `.with_retry` then `.with_fallbacks` to a second model; force a failure and observe the fallback fire.
5. Pass a `RunnableConfig` with tags and metadata, turn on LangSmith tracing, and find those tags on each step.

## Further reading

- LCEL & Runnables: https://docs.langchain.com/oss/python/langchain/lcel
- Runnable interface reference: https://docs.langchain.com/oss/python/langchain/runnables
- Streaming: https://docs.langchain.com/oss/python/langchain/streaming
