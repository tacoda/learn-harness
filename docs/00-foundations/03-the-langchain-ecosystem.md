# 03 · The LangChain Ecosystem & Package Layout

## Mental model

The ecosystem is **many small packages, not one monolith.** Understanding the package boundaries tells you where any given class lives and why an import path is what it is. The boundaries also *are* the architecture: core abstractions are isolated from integrations so that providers can be swapped without touching your logic.

## The package map

```
langchain-core        ← the interfaces: Runnable, BaseChatModel, BaseTool, BaseMessage,
                          prompts, output parsers, callbacks. No provider code. Rarely
                          imported directly, but everything depends on it.
langchain             ← the batteries: create_agent, init_chat_model, middleware,
                          high-level retrieval helpers. This is your main import.
langchain-<provider>  ← integrations: langchain-anthropic, langchain-openai,
                          langchain-ollama, etc. One package per provider.
langgraph             ← the runtime: StateGraph, prebuilt agents, checkpointers,
                          store, interrupts, streaming.
langgraph-checkpoint-*← persistence backends (sqlite, postgres).
langsmith             ← tracing client, @traceable, evaluate, datasets.
langchain-community   ← the long tail of community integrations (many loaders,
                          vectorstores). Lower-support, use deliberately.
```

### Why `langchain-core` exists

Every abstraction you compose — a model, a tool, a retriever, a parser — implements the `Runnable` interface defined in `langchain-core`. That single interface (`.invoke`, `.stream`, `.batch`, `.ainvoke`, …) is what lets you pipe components together and is what LangGraph nodes call under the hood. When you understand that "a chat model is a Runnable" and "a tool is a Runnable," the whole ecosystem collapses into one composable shape. We go deep on this in the LangChain track (`04-runnables-and-lcel.md`).

### Why providers are separate packages

`langchain-core` defines `BaseChatModel`; `langchain-anthropic` implements it as `ChatAnthropic`. Your code depends on the *interface*, so switching from Anthropic to OpenAI is a one-line model swap, not a rewrite. This is the single most important architectural payoff of the whole ecosystem — and it's why `init_chat_model("claude-...")` vs `init_chat_model("gpt-...")` is all it takes to change providers.

## `init_chat_model`: the universal entry point

Rather than importing a specific provider class, prefer:

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("claude-sonnet-4-6", temperature=0)
# or "gpt-5-mini", "ollama:llama3.1", ...
```

This keeps provider choice a string/config concern and is the pattern the rest of the course uses. Import the concrete class (`ChatAnthropic`) only when you need provider-specific constructor args.

## Versioning & release cadence

- The v1 line (`langchain>=1.0`, `langgraph>=1.0`) is the current supported major. Pin to it.
- Integrations version independently of core — `langchain-anthropic` can release without `langchain` releasing. This is why you sometimes upgrade one package and not the others.
- LangSmith SDK versions independently of everything; it's a client for a hosted service.

## How the pieces talk to each other

1. You build components from `langchain` (models, tools, prompts).
2. `create_agent` wires them into a **LangGraph graph** and returns a compiled `Runnable`.
3. When you invoke it, LangGraph executes the graph node-by-node, checkpointing state if configured.
4. If `LANGSMITH_TRACING=true`, every step emits a run to **LangSmith**, giving you a tree-view trace.
5. You collect real inputs into a **LangSmith dataset**, write evaluators, and run experiments to gate changes.

That loop — build → run → trace → evaluate → improve — is the spine of the whole course.

## Pitfalls

- **`langchain-community` for critical paths.** It's a grab-bag of varying quality. For production, prefer first-party integration packages where they exist.
- **Mixing v0.x and v1 packages.** If `langchain` is v1 but a tutorial pulls a v0 integration, imports will fight. Keep the whole set on the v1 line.
- **Importing from `langchain-core` directly for everyday work.** You usually want the re-exports from `langchain`; reach into core only for interface types (e.g. `BaseMessage` subclasses).

## Exercises

1. `uv add langchain langchain-anthropic langgraph langsmith`, then `uv tree` — read the dependency graph and locate `langchain-core`.
2. Swap a working `init_chat_model("claude-...")` call to an OpenAI model and confirm nothing else changes.
3. Given an import like `from langgraph.checkpoint.sqlite import SqliteSaver`, name which package provides it.

## Further reading

- Package/architecture overview: https://docs.langchain.com/oss/python/langchain/overview
- `init_chat_model` reference: https://docs.langchain.com/oss/python/langchain/models
- LangGraph library structure: https://docs.langchain.com/oss/python/langgraph/overview
