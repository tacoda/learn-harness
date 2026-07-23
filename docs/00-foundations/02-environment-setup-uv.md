# 02 · Environment Setup with uv

## Mental model

Every module in `examples/` is its own **standalone `uv` project** — its own `pyproject.toml`, its own locked dependency set, its own `.venv`. This is deliberate: the LangChain ecosystem moves fast and pins matter. Isolating modules means one example's dependency bump never breaks another, and each `uv.lock` is a reproducible record of exactly what versions the code was written against.

`uv` is the tool for this. It replaces `pip`, `venv`, `pip-tools`, and `pyenv` with one fast binary, and it makes per-project environments cheap.

## Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# verify
uv --version   # expect 0.5+
```

## Create a module project

From inside `examples/`:

```bash
uv init --python 3.12 01-chat-models
cd 01-chat-models
uv add "langchain>=1.0" "langchain-anthropic" "langgraph>=1.0" "langsmith"
```

`uv add` resolves, installs into a local `.venv`, and writes both `pyproject.toml` and `uv.lock`. Run anything with `uv run`, which auto-syncs the env first:

```bash
uv run python main.py
uv run pytest
```

There is no "activate the venv" step — `uv run` is the entry point. (You *can* `source .venv/bin/activate` if you prefer, but you won't need to.)

## Dependencies you'll use across the course

| Package | Role |
|---|---|
| `langchain` | building blocks + `create_agent` |
| `langchain-anthropic` / `langchain-openai` | model provider integrations (install what you use) |
| `langgraph` | the orchestration runtime |
| `langgraph-checkpoint-sqlite` / `-postgres` | durable persistence backends |
| `langsmith` | tracing + evaluation client |
| `openevals` | prebuilt LLM-as-judge evaluators |
| `deepagents` | the deep-agents layer (later track) |
| `python-dotenv` | load `.env` in examples |

Provider packages are **separate installs** on purpose — LangChain core stays provider-agnostic, and you pull in only the integrations you use.

## Secrets and configuration

Create a `.env` at the repo root (already git-ignored — see below) and load it in examples:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# LangSmith tracing — turning this on traces every LangChain/LangGraph run
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=learn-harness
```

```python
from dotenv import load_dotenv
load_dotenv()  # now os.environ has your keys
```

Setting `LANGSMITH_TRACING=true` is all it takes to get full traces of every model call, tool call, and graph step in the LangSmith UI — no code changes. Do this from module 1 so you *see* what every abstraction is doing.

## .gitignore

```gitignore
.venv/
__pycache__/
*.pyc
.env
.langgraph_api/     # local LangGraph dev server state
*.sqlite            # local checkpointer dbs
```

## Sanity check

```python
# main.py
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()
model = init_chat_model("claude-sonnet-4-6")   # or "gpt-5-mini"
print(model.invoke("Reply with the single word: ready").content)
```

```bash
uv run python main.py   # -> ready
```

If that prints `ready` and the run shows up in your LangSmith project, your environment is correct and you can start module 1.

## Pitfalls

- **Global installs.** Don't `pip install langchain` into a system Python. Per-project `uv` envs keep versions honest.
- **Missing provider package.** `init_chat_model("claude-...")` fails until `langchain-anthropic` is installed. The error names the package to add.
- **Forgetting `uv run`.** Running `python main.py` directly uses whatever Python is on PATH, not the project env.
- **Committing `.env`.** Never. Keys leak permanently once pushed.

## Exercises

1. Create the module-1 project and get the sanity check printing `ready`.
2. Turn on `LANGSMITH_TRACING` and confirm the call appears in the LangSmith UI.
3. Run `uv lock --upgrade` in a throwaway copy and diff `uv.lock` — see what pins moved.

## Further reading

- uv docs: https://docs.astral.sh/uv/
- `init_chat_model`: https://docs.langchain.com/oss/python/langchain/models
- LangSmith tracing setup: https://docs.langchain.com/langsmith/observability-quickstart
