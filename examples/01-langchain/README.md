# 01 · LangChain

Runnable examples for the `docs/01-langchain` track, targeting **LangChain 1.x / LangGraph 1.x** with OpenAI as the provider. Each script is self-contained, uses current v1 APIs only (no `AgentExecutor`, `initialize_agent`, or `LLMChain`), and carries a small `assert`-based self-check where it has non-trivial non-LLM logic.

## What it covers

The core of the v1 library: chat models, prompt templates, structured output, LCEL composition, tool calling, retrieval and RAG, and the `create_agent` stack (agents, middleware, streaming).

## Setup

This is a standalone `uv` project. It reads `OPENAI_API_KEY` and `MODEL` from the repo-root `.env` (loaded via `python-dotenv`'s `find_dotenv()`); copy `.env.example` to `.env` at the repo root first.

```bash
cd examples/01-langchain
uv sync                              # create .venv, install locked deps
uv run python 01_chat_models.py      # uv run auto-syncs after the first sync
```

`MODEL` defaults to `gpt-4o-mini`; change it in `.env` to use any OpenAI chat model you have access to.

## Scripts

| Script | Doc | Demonstrates |
|---|---|---|
| `01_chat_models.py` | `01-chat-models-and-messages.md` | `init_chat_model`; `invoke` / `stream` / `batch`; message objects vs. dicts vs. bare string |
| `02_prompt_templates.py` | `02-prompt-templates.md` | `ChatPromptTemplate` with a `MessagesPlaceholder`; `prompt \| model`; `.partial` |
| `03_structured_output.py` | `03-structured-output.md` | Pydantic model + `with_structured_output`; typed result with a field-type assertion |
| `04_runnables_lcel.py` | `04-runnables-and-lcel.md` | `prompt \| model \| StrOutputParser`; `RunnableParallel`; `.batch` |
| `05_tools_and_calling.py` | `05-tools-and-tool-calling.md` | `@tool` + `bind_tools`; one manual round: model picks tool, execute, feed `ToolMessage` back |
| `06_retrieval.py` | `06-retrieval-embeddings-vectorstores.md` | `RecursiveCharacterTextSplitter` → `OpenAIEmbeddings` → `InMemoryVectorStore` → retriever |
| `07_rag.py` | `07-rag-patterns.md` | Naive RAG: retriever + prompt + model as an LCEL chain grounded in context |
| `09_agent.py` | `09-agents-create-agent.md` | `create_agent` with two tools; runs the loop; reads the final message |
| `10_middleware.py` | `10-middleware.md` | Custom `@before_model` hook + built-in `SummarizationMiddleware` |
| `11_streaming.py` | `11-streaming.md` | Agent streaming with `stream_mode` `"updates"` and `"messages"` (v2 schema) |
