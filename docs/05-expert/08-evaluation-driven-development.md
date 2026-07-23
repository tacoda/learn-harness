# 08 · Evaluation-Driven Development

## Mental model

LLM outputs are non-deterministic, which makes "did my change help?" genuinely hard to answer — the same input can produce different outputs, and eyeballing a few runs tells you nothing statistically. Evaluation-driven development is the answer: **treat evals as tests.** A test suite you run to gate changes, built from real data, measuring the properties you actually care about. This is Loop 4 from `01-the-agent-loop-and-loop-engineering.md` — build → trace → eval → improve — elevated from an occasional activity to a *development discipline*.

The parallel to TDD is exact and worth holding onto:

| TDD | Evaluation-driven development |
|---|---|
| Write a failing test | Add a failing example to the dataset (often from a production incident) |
| Make it pass | Fix the agent until it passes |
| Regression suite gates merges | Eval suite gates merges in CI |
| Red/green is deterministic | Scores are distributions; gate on aggregate metrics |

The crucial difference: eval scores are *distributions, not booleans*. You don't gate on "this one run passed"; you gate on "the aggregate score over the dataset didn't regress." That statistical framing is what makes evals trustworthy on non-deterministic systems.

## In depth

### Golden datasets from production traces

The single most important practice: **build your datasets from real production traces, not synthetic inputs.** A dataset is a collection of examples, each an input plus (optionally) a reference output. Synthetic datasets test the inputs you imagined; production-harvested datasets test the inputs users actually send — including the weird ones that break things.

The workflow: LangSmith traces every production run (`docs/03-langsmith/01-tracing-and-observability.md`); you triage runs (often via annotation queues, `docs/03-langsmith/07-annotation-queues-and-feedback.md`); the interesting ones — failures, edge cases, near-misses — get exported into a dataset as examples. Every incident becomes a permanent regression test. Over time your "golden set" becomes the distilled memory of everything that's ever gone wrong, and the gate that stops it recurring. See `docs/03-langsmith/02-datasets.md`.

### Offline vs. online evaluation

Two complementary modes, and mature systems run both:

- **Offline** evaluation runs against a fixed dataset with reference outputs, before you ship. This is your CI gate and your development loop — deterministic in *what* it tests (the dataset is fixed), even though outputs vary. Run with `client.evaluate(...)`.
- **Online** evaluation runs against live production runs, which have *no* reference outputs. Online evaluators must judge quality reference-free — safety checks, quality heuristics, "does this response contain PII," "is it on-topic." Online eval surfaces issues that then become offline test cases, closing the loop.

LangChain frames these as an iterative feedback loop: online eval finds problems → they become offline examples → offline eval validates the fix → online eval confirms the improvement in production. Neither mode alone is sufficient.

### `client.evaluate` — the offline gate

The offline experiment API in the current LangSmith SDK:

```python
from langsmith import Client

client = Client()

def target(inputs: dict) -> dict:
    return {"answer": my_agent.invoke({"messages": [("user", inputs["question"])]})}

results = client.evaluate(
    target,                        # your app under test
    data="support-golden-set",     # the dataset
    evaluators=[correctness, no_pii, tone],
    experiment_prefix="fix-routing-bug",
)
```

Each run against the dataset is scored by every evaluator; LangSmith aggregates the scores into an experiment you can compare against previous experiments. "Did my change help?" becomes "did experiment B beat experiment A on the metrics I care about?" — an answerable, comparable question. See `docs/03-langsmith/03-evaluation-and-experiments.md`.

### Kinds of evaluators

- **Code evaluators** — deterministic, rule-based functions: does the JSON parse, does the code compile, is the classification an exact match, is the response non-empty. Cheap, fast, unambiguous. Prefer these whenever the property is checkable in code.
- **LLM-as-judge** — an LLM scores the output against a rubric encoded in its prompt. Reference-free (does it contain offensive content? does it meet criteria?) or reference-based (is it factually consistent with the reference?). The tool for properties too fuzzy for code — helpfulness, tone, faithfulness. See `docs/03-langsmith/04-evaluators-llm-as-judge.md`.
- **Human evaluators** — annotation queues and pairwise comparison for the properties a machine can't yet judge, and for calibrating the LLM judges.

### Calibrating LLM-as-judge

An LLM judge is itself a non-deterministic system, so it needs its own evaluation. LangChain's guidance: LLM-as-judge scores require careful review and prompt tuning, and **few-shot judges** — grader prompts that include examples of inputs, outputs, and correct grades — measurably improve reliability. The calibration workflow:

1. Have humans grade a sample.
2. Run the LLM judge on the same sample.
3. Measure agreement between judge and humans.
4. Tune the judge's rubric and few-shot examples until agreement is acceptable.
5. Only then trust the judge to grade at scale.

An uncalibrated judge is a random-number generator with a plausible explanation. Treat the judge as code that itself needs tests.

### Evaluating multi-step traces

Agents don't just produce a final answer — they take a *trajectory* of steps, and a right answer reached by a broken path is a latent bug. Evaluate the intermediate steps, not only the output:

- **Trajectory / tool-use evaluation** — did the agent call the right tools, in a sensible order, without redundant or wrong calls? A correct answer that took 15 flailing tool calls is a reliability and cost problem the final-output score won't catch.
- **Thread-level evaluation** — for multi-turn conversations, evaluate the whole thread: coherence across turns, staying on topic, resolving the user's actual need over the interaction, not just per-turn quality.

Because every step is a span in the trace, and the trace *is* the trajectory, you evaluate agents by evaluating their traces. This is why tracing is a prerequisite for real agent evaluation, not a separate concern.

### The loop as a discipline

Evaluation-driven development is not "we ran evals once before launch." It's a cadence baked into how the team works:

1. Every production incident → a new dataset example.
2. Every change → run the offline suite; gate the merge on no regression (`docs/03-langsmith/08-testing-in-ci-cd.md`).
3. Every deploy → online evaluators watch production; new failures feed back to step 1.

The unit of work is the loop, not the single run (`docs/00-foundations/04-the-langchain-way-philosophy.md`, idiom 8). A team that internalizes this ships confidently; a team without it ships on vibes and finds out from users.

## Why it matters

Without evals, "improving" an agent is guessing — you change a prompt, spot-check three outputs, and hope. Non-determinism means your spot-check is nearly meaningless. Evals convert hope into evidence: a measured, comparable, regression-gated answer to "is this version better?" This is the discipline that lets a team change an agent *safely* — which, per the guiding principle of this whole course, is the entire point. An agent you can't evaluate is an agent you can't safely change.

## Pitfalls

- **No dataset, or a synthetic one.** Evals against inputs you invented miss the inputs that actually break. Harvest from production traces.
- **Gating on a single run.** Outputs are distributions; gate on aggregate metrics over the dataset, not one pass/fail.
- **Trusting an uncalibrated LLM judge.** A judge you haven't checked against human grades is noise. Calibrate with few-shot examples and agreement measurement.
- **Only scoring the final output.** A right answer via a broken trajectory is a hidden bug. Evaluate intermediate steps and tool use.
- **Evals as a one-time launch gate.** The value is in the *loop* — incident → example → fix → gate → deploy → monitor. Run it continuously.
- **No CI gate.** Evals you don't enforce don't prevent regressions. Wire the suite into CI.

## Exercises

1. Export 15 real (or realistic) traces from an agent into a LangSmith dataset, including at least three known failures. Write one code evaluator and one LLM-as-judge evaluator, and run `client.evaluate`.
2. Calibrate your LLM judge: hand-grade 10 examples, run the judge on the same 10, measure agreement, and iterate the rubric/few-shot examples until agreement is acceptable. Report the before/after agreement.
3. Add a trajectory evaluator that checks the agent called an expected tool and did *not* make redundant calls. Find a case where the final answer is correct but the trajectory evaluator fails.
4. Wire the offline eval suite into CI as a merge gate. Make a deliberately-regressing change and confirm the gate blocks it.

## Further reading

- Evaluation concepts (offline/online, evaluator types, LLM-as-judge, threads): https://docs.langchain.com/langsmith/evaluation-concepts
- LangSmith track: `docs/03-langsmith/02-datasets.md`, `03-evaluation-and-experiments.md`, `04-evaluators-llm-as-judge.md`, `07-annotation-queues-and-feedback.md`, `08-testing-in-ci-cd.md`
- Tracing (traces are the trajectory you evaluate): `docs/03-langsmith/01-tracing-and-observability.md`
