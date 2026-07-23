# 05-expert — runnable examples

Standalone `uv` project mirroring `docs/05-expert/`. Each script demonstrates one
expert-level pattern for building reliable, affordable LangChain 1.x / LangGraph
1.x agents, using current v1 APIs only (no `AgentExecutor`). Provider is OpenAI
via `init_chat_model(MODEL, model_provider="openai")`.

## Coverage

- **Loop engineering** — bounding an agent/graph loop so it cannot run away, with
  both a soft step-budget guard and a hard `recursion_limit`.
- **Agent design patterns** — the router/classifier pattern (cheap router, strong
  worker) and the evaluator-optimizer (reflection) loop.
- **Production reliability** — `.with_retry(...)` and `.with_fallbacks([...])` as
  composable resilience wrappers on any Runnable.
- **Cost & latency optimization** — measuring a naive path against a cheap-model
  prefilter and comparing latency and estimated cost.

## Setup

One `.env` at the repo root serves every track (see the root `.env.example`).
Set `OPENAI_API_KEY`; `MODEL` defaults to `gpt-4o-mini`. Two scripts also read an
optional `CHEAP_MODEL` for cost tiering — it defaults to `MODEL` when unset, so
everything runs out of the box on a single model.

```bash
cd examples/05-expert
uv sync                              # create .venv, install locked deps
uv run python 01_bounded_loop.py
```

`uv run` auto-syncs, so after the first `uv sync` you can just
`uv run python <script>.py`.

## Scripts

| Script | Demonstrates | Doc |
| --- | --- | --- |
| `01_bounded_loop.py` | Soft step-budget guard + hard `recursion_limit` bounding a graph loop | `docs/05-expert/01-the-agent-loop-and-loop-engineering.md` |
| `02_router_pattern.py` | Cheap classifier routes to a strong specialized handler (cost tiering) | `docs/05-expert/04-agent-design-patterns.md` |
| `03_reflection.py` | Evaluator-optimizer loop: generate → critique → revise, bounded | `docs/05-expert/04-agent-design-patterns.md` |
| `04_retry_fallback.py` | `.with_retry(...)` and `.with_fallbacks([...])` composed on Runnables | `docs/05-expert/06-production-reliability.md` |
| `05_cost_latency.py` | Timed naive vs. cheap-model-prefilter cost/latency comparison | `docs/05-expert/07-cost-and-latency-optimization.md` |

Each script is self-contained, prints its result, and carries an `assert`-based
self-check over its non-LLM logic (loop bounds, dispatch, retry counts, cost
aggregation) so a broken change fails loudly.
