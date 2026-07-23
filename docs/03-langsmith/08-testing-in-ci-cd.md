# 08 · Testing in CI/CD

## Mental model

Everything in files 02–04 was interactive: you run an experiment, look at scores, decide. CI/CD makes that automatic and blocking. The goal is a **regression gate**: a pull request that makes your LLM system worse should fail the build, the same way a PR that breaks a unit test does.

LangSmith gives you two on-ramps into CI, at different altitudes:

```
pytest integration      ← per-test-case eval, familiar assert-based, fine-grained
   │                        `pip install "langsmith[pytest]"`
client.evaluate() in CI ← whole-dataset experiment, threshold on the aggregate score
```

The mental shift for teams new to this: an LLM eval in CI is *not* a pass/fail equality check. It is a threshold on a graded score. "Correctness must be `>= 0.85` on the golden set" is the gate. You are asserting on a distribution's summary, not on an exact string, because the system is non-deterministic.

## In depth

### The pytest integration

Install the plugin and mark tests. Each marked test becomes a LangSmith-tracked case:

```bash
pip install -U "langsmith[pytest]"
```

```python
import pytest
from langsmith import testing as t

@pytest.mark.langsmith
def test_sql_generation_select_all() -> None:
    user_query = "Get all users from the customers table"
    t.log_inputs({"user_query": user_query})            # optional: example inputs
    expected = "SELECT * FROM customers;"
    t.log_reference_outputs({"sql": expected})           # optional: reference

    sql = generate_sql(user_query)
    t.log_outputs({"sql": sql})                          # optional: actual output

    t.log_feedback(key="valid_sql", score=is_valid_sql(sql))   # optional: graded feedback
    assert sql == expected      # pass/fail auto-logged under the 'pass' feedback key
```

What the plugin does:

- `@pytest.mark.langsmith` syncs the test to LangSmith as a tracked case, and the test's pass/fail status is automatically logged under the `pass` feedback key.
- `t.log_inputs`, `t.log_reference_outputs`, `t.log_outputs` record the data for each case (and update the corresponding dataset example). Repeated calls overwrite.
- `t.log_feedback` attaches graded scores — this is how you record a soft metric (`valid_sql = 0.8`) alongside the hard `assert`.
- The plain `assert` is still your gate. It fails the test the ordinary pytest way; LangSmith just also records the outcome.

This altitude is right when you have discrete, nameable cases and want them to read like normal tests, with the LangSmith UI as a bonus dashboard over your test suite.

### Rich output and caching

```bash
pytest --langsmith-output tests          # live-updating results table in LangSmith
```

`--langsmith-output` uploads a rich, live table of results (it replaced the older `--output=langsmith` flag). For CI, enable HTTP caching so you are not paying for and waiting on real model calls on every run:

```bash
LANGSMITH_TEST_CACHE=tests/cassettes pytest --langsmith-output tests
```

`LANGSMITH_TEST_CACHE` records model HTTP requests to disk (cassettes) and replays them, which makes CI fast, deterministic, and cheap. Commit the cassettes and refresh them intentionally when the prompt or model changes.

### Dataset-level evaluation in CI

The other on-ramp is to run a full `client.evaluate` experiment (file 03) inside a CI job and gate on the aggregate score:

```python
from langsmith import Client

def test_correctness_gate():
    client = Client()
    results = client.evaluate(
        target,
        data="Support QA",
        evaluators=[correctness],
        experiment_prefix=f"ci-{os.environ['GIT_SHA']}",
        max_concurrency=4,
    )
    score = mean(r["evaluation_results"]... )   # aggregate the correctness feedback
    assert score >= 0.85, f"correctness {score:.2f} below 0.85 gate"
```

Use this altitude when the unit of truth is the dataset as a whole, not individual named cases. The `experiment_prefix` keyed to the git SHA means each CI run leaves a labeled experiment in LangSmith you can open and compare against previous commits.

### Regression gates and thresholds

A gate is a threshold plus a decision to fail the build. Two flavors:

- **Absolute threshold** — "correctness `>= 0.85`." Simple, but a fixed bar can be too strict (blocks a legitimately hard PR) or too loose (lets slow decay through).
- **Relative / no-regression threshold** — "correctness must not drop more than 2 points below the `main` baseline." Compares this PR's experiment to the baseline experiment. Catches regressions without demanding perfection.

Relative gates are usually the better default because they track "did *this change* make things worse," which is the actual question a PR gate asks. Store the baseline as a known experiment (e.g. the last run on `main`) and compare against it.

### Wiring into the pipeline

The shape of a CI job:

1. Set `LANGSMITH_API_KEY` (and `LANGSMITH_TEST_CACHE` for cached runs) as CI secrets/config.
2. On each PR, run `pytest --langsmith-output` (or the `evaluate`-based gate job).
3. A failed `assert` / threshold breach fails the job, which blocks the merge.
4. Post the LangSmith experiment link as a PR comment so a human can open the comparison view (file 03) and see exactly which examples regressed.

## Why it matters

Without a gate, eval is a thing someone runs when they remember to, and quality decays one un-reviewed PR at a time — each change looks fine in isolation, and the aggregate slowly rots. A CI gate makes "does this regress the eval set?" a mandatory, automatic question on every change, exactly like type-checking or unit tests. That is the difference between an eval suite you *have* and an eval suite that actually *protects* you.

Caching matters because an ungated cost and latency for real model calls on every CI run makes teams disable the gate to keep the pipeline fast — and a disabled gate protects nothing. Cassettes keep the gate cheap enough to leave on.

## Pitfalls

- **Exact-match asserts on generative output.** Asserting `output == "the exact string"` on a free-form generation fails on trivial rewordings. Gate on a graded evaluator's score, not string equality, unless the output truly is deterministic (like structured SQL).
- **No caching in CI.** Real model calls on every run make CI slow, flaky (provider hiccups), and expensive. Use `LANGSMITH_TEST_CACHE` and commit cassettes.
- **Absolute thresholds only.** A fixed bar blocks hard-but-acceptable PRs and misses slow decay. Prefer a no-regression-vs-baseline gate.
- **Flaky thresholds set at the noise floor.** A gate at `>= 0.84` when scores naturally vary between 0.83 and 0.87 fails randomly. Leave headroom and account for judge/model variance.
- **Gate with no visibility.** A red build that just says "eval failed" is useless. Post the experiment link so reviewers can open the comparison view and see the regressed examples.
- **Stale cassettes.** Cached HTTP responses that no longer reflect the current prompt/model give false passes. Refresh cassettes when you change the prompt or model.

## Exercises

1. Install `langsmith[pytest]`, write one `@pytest.mark.langsmith` test that logs inputs/outputs and asserts on a deterministic result, and run it with `--langsmith-output`. Find the case in the LangSmith UI.
2. Enable `LANGSMITH_TEST_CACHE`, run the suite twice, and confirm the second run makes no real model calls. Explain why this matters for CI.
3. Write a CI-style test that runs `client.evaluate` over a small dataset and asserts the aggregate correctness is above a threshold. Make it fail by lowering the bar unrealistically high, then set a sane bar.
4. Design a no-regression gate that compares a PR's experiment to the `main` baseline. State the threshold, where the baseline is stored, and how you would surface the result on the PR.

## Further reading

- Test with pytest: https://docs.langchain.com/langsmith/pytest
- Evaluation in CI/CD: https://docs.langchain.com/langsmith/evaluation-quickstart
- Test caching: https://docs.langchain.com/langsmith/pytest
- Compare experiment results: https://docs.langchain.com/langsmith/compare-experiment-results
