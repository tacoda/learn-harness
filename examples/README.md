# examples

Runnable code mirroring the `docs/` tracks. Each track is a **standalone `uv` project** — its own `pyproject.toml`, its own `.venv`, its own locked deps.

```
examples/
├── 01-langchain/     # mirrors docs/01-langchain
├── 02-langgraph/     # mirrors docs/02-langgraph
├── 03-langsmith/     # mirrors docs/03-langsmith
├── 04-deepagents/    # mirrors docs/04-deepagents
├── 05-expert/        # mirrors docs/05-expert
└── 06-production/    # mirrors docs/06-production
```

## Setup (once)

1. Copy the root env template and fill it in — one `.env` at the repo root serves every project:
   ```bash
   cp .env.example .env      # then edit .env: set OPENAI_API_KEY
   ```
   `.env` is git-ignored. Every script loads it via `python-dotenv`'s `find_dotenv()`, which walks up to the repo root.

2. Install `uv` if you haven't: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Running a track

```bash
cd examples/01-langchain
uv sync                       # create .venv, install locked deps
uv run python 01_chat_models.py
```

`uv run` auto-syncs before running — after the first `uv sync` you can just `uv run python <script>.py`.

## Conventions

- Every script names the doc it demonstrates in its top docstring.
- Every script is self-contained and runnable on its own.
- Provider is **OpenAI** via `init_chat_model(MODEL, model_provider="openai")`; `MODEL` comes from `.env` (default `gpt-4o-mini`).
- Scripts with non-trivial logic carry a small `assert`-based self-check so a broken change fails loudly.

> Model note: `.env.example` defaults to `gpt-4o-mini`. Swap `MODEL` in `.env` for any OpenAI chat model you have access to — nothing else changes.
