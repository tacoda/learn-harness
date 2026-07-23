# 04 · deepagents

Runnable examples mirroring `docs/04-deepagents/`. A **deep agent** is the
ordinary LangChain/LangGraph model⇄tools loop with four additions bolted on: a
large system prompt, a planning tool (`write_todos`), sub-agents for context
isolation, and a state-backed virtual filesystem. `create_deep_agent` returns a
compiled LangGraph graph (`CompiledStateGraph`), so everything you know about
LangGraph — invoking with `{"messages": [...]}`, checkpointers, streaming —
applies unchanged.

Built on **deepagents** (LangGraph 1.x + LangChain 1.x). Provider is OpenAI via
`init_chat_model(MODEL, model_provider="openai")`; `MODEL` comes from the root
`.env` (default `gpt-4o-mini`). The current API uses `system_prompt=` (not the
old 0.x `instructions=`) and takes a `model=` argument.

## Coverage

- **Basic deep agent** — one custom `@tool` plus a `system_prompt`, invoked with
  `{"messages": [...]}`.
- **Sub-agents** — a custom sub-agent declared as a dict (`name` / `description`
  / `system_prompt` / `tools`), with the main agent delegating via the `task`
  tool. Intermediate work stays isolated in the sub-agent's own context window.
- **Virtual filesystem** — the agent writes to state-backed files; we read them
  back out of the returned state's `files` dict.
- **Checkpointing** — an `InMemorySaver` plus a `thread_id` gives a durable,
  multi-turn conversation that remembers earlier turns.

## Setup

Requires the root `.env` with `OPENAI_API_KEY` set (see `examples/README.md`).

```bash
cd examples/04-deepagents
uv sync                             # create .venv, install locked deps
uv run python 01_basic_deep_agent.py
```

`uv run` auto-syncs, so after the first `uv sync` you can just
`uv run python <script>.py`.

## Run commands

```bash
uv run python 01_basic_deep_agent.py
uv run python 02_subagents.py
uv run python 03_filesystem.py
uv run python 04_checkpointed.py
```

## Script → doc

| Script | Doc |
|---|---|
| `01_basic_deep_agent.py` | `docs/04-deepagents/01-what-are-deep-agents.md` |
| `02_subagents.py` | `docs/04-deepagents/03-subagents-and-context-isolation.md` |
| `03_filesystem.py` | `docs/04-deepagents/04-virtual-filesystem.md` |
| `04_checkpointed.py` | `docs/04-deepagents/04-virtual-filesystem.md` (persistence) · `docs/04-deepagents/06-implementing-a-deep-agent.md` |
