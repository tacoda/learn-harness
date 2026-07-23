# 06 · Production

Mirrors `docs/06-production/`. This project is a single, real, deployable agent
plus the promotion/monitoring pattern that surrounds it: **deploy → monitor →
maintain**, with an eval gate on the way to production.

## The pattern

An agent goes to production the same way regardless of how complex it is:

1. **Package** it as a compiled graph exported from a module, declared in a
   `langgraph.json` manifest — the deployable contract
   (`docs/06-production/02-packaging-and-assistants.md`).
2. **Deploy** that manifest to an Agent Server. Locally that server is
   `langgraph dev` (in-memory, disposable); a real deployment is the same
   manifest against a Postgres-backed server
   (`docs/06-production/03-deploying.md`).
3. **Monitor** every run with LangSmith tracing, dashboards, and automation
   rules that harvest failing runs into datasets
   (`docs/06-production/04-monitoring.md`).
4. **Maintain**: promote changes through `local → staging → prod`, and gate each
   promotion on an automated regression eval so a change that makes things worse
   never ships (`docs/06-production/05-maintenance-and-iteration.md`).

This project demonstrates steps 1, 2 (locally), and the gate from step 4.

## Layout

```
06-production/
├── langgraph.json      # the manifest — the deployable contract
├── pyproject.toml      # dependencies
├── app/
│   ├── __init__.py
│   └── agent.py        # exports the compiled `graph` — THE deployable artifact
└── eval_gate.py        # CI-style regression gate (deploy gate)
```

## Run it

Install deps once (from the repo root `.env`, set `OPENAI_API_KEY`, and for the
gate `LANGSMITH_API_KEY` — see `../../.env.example`):

```bash
cd examples/06-production
uv sync
```

### Local dev server

Start the local Agent Server (in-memory, hot reload) on port 2024:

```bash
uv run langgraph dev
```

It serves `http://127.0.0.1:2024`, opens the Studio IDE against it, and serves
interactive API docs at `/docs`. Hit the graph over the API — for example:

```bash
curl -s http://127.0.0.1:2024/assistants/search \
  -H 'content-type: application/json' -d '{}'
```

The graph name is `agent` (the key in `langgraph.json`). Clients speak
Threads/Runs and assistant IDs against it; they never reach into graph state.
Useful flags: `--no-browser`, `--port`, `--no-reload`, `--tunnel`.

### The eval gate

Run the regression gate that a CI pipeline runs before promoting a change:

```bash
uv run python eval_gate.py
```

It builds a tiny LangSmith dataset, evaluates the graph against it, prints the
aggregate score, and **exits non-zero** if the score is below the threshold —
which is what blocks the merge. Without `LANGSMITH_API_KEY` it prints a clear
message and skips (exit 0).

## How this generalises

- **Bigger apps** expose several graphs from one `langgraph.json` and add fields
  (`auth`, `store`, `checkpointer`) — the file scales with the app, the deploy
  mechanism does not change (`docs/06-production/02`).
- **Assistants & versions** separate *code* (the graph, redeploy to change) from
  *config* (an assistant version, change live and roll back instantly). This is
  the canary/rollback mechanism (`docs/06-production/02`, `05`).
- **staging → prod** is the same manifest against a Postgres-backed server, with
  the eval gate on the arrow between stages (`docs/06-production/01`, `03`, `05`).

## Script → doc

| File               | Doc                                                    |
| ------------------ | ------------------------------------------------------ |
| `app/agent.py`     | `02-packaging-and-assistants.md` (the deployable graph)|
| `langgraph.json`   | `02-packaging-and-assistants.md` (the manifest)        |
| `uv run langgraph dev` | `02-packaging-and-assistants.md` / `03-deploying.md` |
| `eval_gate.py`     | `05-maintenance-and-iteration.md` (§③ deploy gate)     |

See `docs/06-production/06-the-production-pattern-checklist.md` for the full
concern → feature map and go-live checklist.
