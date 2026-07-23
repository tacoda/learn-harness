# 03 · LangSmith

Runnable code for the LangSmith track: tracing, datasets, evaluation, LLM-as-judge, and testing in CI. Provider is OpenAI; the LangSmith SDK is current (no 0.x APIs).

## Coverage

| Script | Demonstrates | Doc |
| --- | --- | --- |
| `01_tracing.py` | `@traceable` + `wrap_openai` produce one nested trace | `docs/03-langsmith/01-tracing-and-observability.md`, `09-instrumenting-your-code-traceable.md` |
| `02_dataset.py` | `Client` create_dataset / create_examples / list_examples | `docs/03-langsmith/02-datasets.md` |
| `03_evaluate.py` | `client.evaluate` with a heuristic evaluator | `docs/03-langsmith/03-evaluation-and-experiments.md` |
| `04_llm_judge.py` | openevals `create_llm_as_judge` (CORRECTNESS_PROMPT) as an evaluator | `docs/03-langsmith/04-evaluators-llm-as-judge.md` |
| `test_regression.py` | `langsmith[pytest]` integration (`@pytest.mark.langsmith`) | `docs/03-langsmith/08-testing-in-ci-cd.md` |

## Setup

This track needs a LangSmith API key **and** tracing turned on, in addition to the OpenAI key. In the root `.env` (see `.env.example`):

```
OPENAI_API_KEY=sk-...
MODEL=gpt-4o-mini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=learn-harness
```

`LANGSMITH_TRACING=true` is what makes `@traceable` and auto-tracing actually emit runs; with it unset the scripts still run but send nothing. Every script loads the root `.env` via `python-dotenv`.

## Run

```bash
cd examples/03-langsmith
uv sync                                  # create .venv, install locked deps

uv run python 02_dataset.py              # run first — creates the "Support QA" dataset
uv run python 01_tracing.py
uv run python 03_evaluate.py             # evaluates against "Support QA"
uv run python 04_llm_judge.py            # evaluates against "Support QA"
```

`uv run` auto-syncs first, so after the initial `uv sync` you can just `uv run python <script>.py`. Run `02_dataset.py` before the two evaluate scripts — they score the dataset it creates.

## Run the pytest example

```bash
uv run pytest test_regression.py --langsmith-output
```

The `--langsmith-output` flag renders the rich per-case table. Plain `uv run pytest` also works; each `@pytest.mark.langsmith` test still syncs to LangSmith, logging pass/fail under the `pass` feedback key. Open https://smith.langchain.com to find the tracked cases.

## Notes

- `02_dataset.py` has an `assert`-based self-check on the example count; it creates the dataset idempotently (`has_dataset`) so re-running is safe.
- `03_evaluate.py` and `04_llm_judge.py` print the returned `experiment_name` — open it in the LangSmith UI to compare heuristic vs. LLM-judge scores over the same dataset.
