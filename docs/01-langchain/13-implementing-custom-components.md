# 13 · Implementing Custom Components

## Mental model

Every LangChain abstraction is a **contract**: implement a small set of methods and your object becomes a first-class citizen — pipeable with `|`, streamable, batchable, traceable, and droppable into an agent or graph. This module is the implementer's view: for each core interface, what you must implement, what you get for free, and the lightest way to satisfy the contract. The recurring rule: **implement the sync core method; the async, batch, and streaming variants are derived for you unless you have a reason to override them.**

## In depth

### Custom tool — the easy tier

You've seen it (module 05): `@tool` *is* the custom-tool mechanism. Type hints become the arg schema, the docstring becomes the description. Reach past it only when you need dynamic schemas or bespoke validation — then use `StructuredTool.from_function` or subclass `BaseTool` and implement `_run` (and optionally `_arun`):

```python
from langchain.tools import BaseTool
from pydantic import BaseModel

class SearchTool(BaseTool):
    name: str = "search"
    description: str = "Search the knowledge base."
    args_schema: type[BaseModel] = SearchArgs

    def _run(self, query: str, limit: int = 5) -> str:
        return do_search(query, limit)
    # async def _arun(...) -> str: ...   # optional; sync is wrapped in a thread if omitted
```

### Custom Runnable — two routes

**Route 1: `RunnableLambda`** (prefer this). Any function becomes a Runnable — instant `.invoke`/`.batch`/`.astream`:

```python
from langchain_core.runnables import RunnableLambda

def normalize(text: str) -> str:
    return text.strip().lower()

step = RunnableLambda(normalize)          # now pipeable: prompt | step | model
step.invoke("  HELLO  ")                  # -> "hello"
```

**Route 2: subclass `Runnable`** when you need config-awareness, custom streaming, or your own state. Implement `invoke(self, input, config)`; override `stream` / `ainvoke` only if the defaults (which delegate to `invoke`) aren't good enough:

```python
from langchain_core.runnables import Runnable, RunnableConfig

class RepeatN(Runnable):
    def __init__(self, n: int):
        self.n = n
    def invoke(self, input: str, config: RunnableConfig | None = None) -> str:
        return input * self.n
```

Rule: reach for `RunnableLambda` for pure functions; subclass only when you need to accept config, hold state, or stream natively.

### Custom chat model — `BaseChatModel`

To integrate a provider or wrap a bespoke endpoint, subclass `BaseChatModel`. The one method you *must* implement is `_generate` (messages → `ChatResult`); implement `_stream` for token streaming and set `_llm_type`:

```python
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

class EchoChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "echo"

    def _generate(self, messages: list[BaseMessage], stop=None,
                  run_manager=None, **kwargs) -> ChatResult:
        text = messages[-1].content
        msg = AIMessage(content=f"echo: {text}")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    # def _stream(self, messages, ...): yield ChatGenerationChunk(...)  # for token streaming
```

Implement `_generate` and you get `.invoke`/`.batch`/`.bind_tools`/`with_structured_output` scaffolding for free; add `_stream` and `.stream` works too. The `run_manager` is how your model reports tokens to the callback system — thread it through so tracing works.

### Custom retriever — `BaseRetriever`

Implement `_get_relevant_documents` (query → `list[Document]`); the public `.invoke`, callbacks, and async wrapping come for free:

```python
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

class KeywordRetriever(BaseRetriever):
    corpus: list[str]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        hits = [t for t in self.corpus if query.lower() in t.lower()]
        return [Document(page_content=t) for t in hits]
```

Because it's a `BaseRetriever`, the result is a Runnable — it pipes into the RAG chain shape (module 06/07) and shows up in traces as a retriever step with no extra work.

### Custom output parser

Parsers turn a model's message into a typed value. For most needs, compose an existing one (`StrOutputParser`, `PydanticOutputParser`, `JsonOutputParser`) — or, since a parser is just a Runnable, a `RunnableLambda`. To build a real one, subclass `BaseOutputParser` and implement `parse` (str → your type); `get_format_instructions` supplies the "reply in this format" text you inject into the prompt:

```python
from langchain_core.output_parsers import BaseOutputParser

class CSVListParser(BaseOutputParser[list[str]]):
    def parse(self, text: str) -> list[str]:
        return [item.strip() for item in text.split(",") if item.strip()]

    def get_format_instructions(self) -> str:
        return "Reply with a comma-separated list, nothing else."
```

### The through-line: implement the core, inherit the rest

| Interface | Must implement | Free once you do |
|---|---|---|
| `BaseTool` | `_run` | schema, `.invoke`, async, tracing |
| `Runnable` (subclass) | `invoke` | `batch`, default `stream`/`ainvoke` |
| `BaseChatModel` | `_generate` | `.invoke`/`.batch`/`bind_tools`/structured output |
| `BaseRetriever` | `_get_relevant_documents` | `.invoke`, async, retriever tracing |
| `BaseOutputParser` | `parse` | pipeable, `get_format_instructions` hook |

The library implements the *fan-out* methods (batch, async, streaming) in terms of your *one* core method, and threads the callback `run_manager` through so your component is observable automatically. That's the entire design: you write the irreducible logic, the base class supplies the interface.

## Why it matters

The "implement one method, inherit the interface" contract is what makes LangChain **extensible without forking it**. A custom retriever you write today pipes into chains, gets traced in LangSmith, streams, and runs async — not because you wrote that plumbing, but because you satisfied the `BaseRetriever` contract and the base class did. The tradeoff is discipline: the base classes expect you to thread `run_manager` and honor `config`, and skipping that quietly breaks tracing, cancellation, and concurrency limits for everything downstream. Get the contract right and your component is indistinguishable from a built-in; get it half-right and it works in isolation but goes dark in a trace.

## Pitfalls

- **Subclassing `Runnable` when `RunnableLambda` would do.** A pure function needs no class. Reserve subclassing for config-awareness, state, or native streaming.
- **Overriding async/batch by hand unnecessarily.** The base classes derive them from your sync core. Only override when you have a genuinely better async path — otherwise you risk divergent behavior between sync and async.
- **Dropping `run_manager` / `config`.** If your `_generate` or `_get_relevant_documents` ignores the run manager, your component won't emit callbacks — it goes invisible in LangSmith and ignores cancellation.
- **Forgetting `_stream` on a custom chat model.** Without it, `.stream` falls back to emitting the whole response as one chunk. Implement `_stream` for real token streaming.
- **Custom parser with no `get_format_instructions`.** The model won't know the target format, so `parse` fails on free-form text. Provide instructions and inject them into the prompt.
- **Reinventing tools.** `@tool` covers the overwhelming majority of cases. Subclass `BaseTool` only for dynamic schemas or custom validation you truly can't express with the decorator.
- **Assuming old `LLM` / base-class paths.** In v1 the base classes live under `langchain_core.*` (`language_models`, `retrievers`, `output_parsers`, `runnables`). Old tutorials import from moved locations.

## Exercises

1. Wrap a pure function as a `RunnableLambda`, pipe it into `prompt | model | lambda`, and confirm `.batch` and `.astream` work without extra code.
2. Subclass `BaseChatModel` with `_generate` only; then add `_stream` and demonstrate token streaming turning on.
3. Implement a `BaseRetriever` over an in-memory list and drop it into the module-07 RAG chain; find its step in a trace.
4. Write a `BaseOutputParser` subclass with `parse` + `get_format_instructions`; inject the instructions into a prompt and verify round-trip parsing.
5. Deliberately omit `run_manager` from a custom retriever, then add it back, and compare what appears in LangSmith.

## Further reading

- Custom Runnables: https://docs.langchain.com/oss/python/langchain/runnables
- Custom chat models: https://docs.langchain.com/oss/python/integrations/chat
- Custom retrievers: https://docs.langchain.com/oss/python/integrations/retrievers
- Custom tools: https://docs.langchain.com/oss/python/langchain/tools
- Output parsers: https://docs.langchain.com/oss/python/langchain/structured-output
