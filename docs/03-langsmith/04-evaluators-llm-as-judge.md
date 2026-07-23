# 04 · Evaluators & LLM-as-Judge

## Mental model

An evaluator is a scoring function with a fixed signature:

```python
def my_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> bool | float | dict:
    ...
```

It receives one example's inputs, your system's outputs, and the dataset's reference outputs, and returns a score. That score is attached to the run as **feedback** under a named **feedback key** (e.g. `correctness`, `tone`). The feedback key is what shows up as a column in the experiment table and what you aggregate and compare over time.

There are two families:

- **Heuristic evaluators** — plain code. Exact match, regex, JSON-validity, length checks, contains-substring, latency thresholds. Deterministic, free, instant, unarguable. Use them wherever the correctness criterion is mechanical.
- **LLM-as-judge evaluators** — a model grades the output against a rubric. Necessary when correctness is semantic ("is this answer faithful to the context?", "is the tone appropriate?") and no heuristic can capture it.

The rule of thumb: reach for a heuristic first, always. Only escalate to an LLM judge when the property you are grading genuinely requires understanding meaning. A judge is slower, costs money, and is itself fallible — it is a tool of last resort, not a default.

## In depth

### Return types and feedback keys

An evaluator can return:

- a `bool` or `float` — scored under the function's name as the feedback key;
- a `dict` like `{"key": "correctness", "score": 0.9, "comment": "..."}` — explicit key, optional comment;
- a list of such dicts — one evaluator emitting multiple feedback keys at once.

Naming the key explicitly (via the dict form or the judge's `feedback_key` argument) is best practice: the key becomes a column header and a time series you will track for the life of the project, so give it a stable, meaningful name.

### Heuristic evaluators

```python
def exact_match(outputs: dict, reference_outputs: dict) -> bool:
    return outputs["answer"] == reference_outputs["answer"]

def is_json(outputs: dict) -> dict:
    import json
    try:
        json.loads(outputs["answer"])
        return {"key": "valid_json", "score": 1.0}
    except Exception:
        return {"key": "valid_json", "score": 0.0}
```

Note the signature is flexible: you only declare the parameters you use. An evaluator that does not need the reference can omit `reference_outputs`; one that does not need inputs can omit `inputs`. LangSmith inspects the signature and passes what you ask for.

### LLM-as-judge with openevals

`openevals` is the batteries-included library of prebuilt judges and prompts. The most common path:

```python
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

def correctness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict):
    judge = create_llm_as_judge(
        prompt=CORRECTNESS_PROMPT,   # a vetted rubric prompt
        model="openai:o3-mini",      # the judge model
        feedback_key="correctness",  # names the feedback
    )
    return judge(
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )
```

`openevals` ships prompts for common axes (correctness, conciseness, hallucination, RAG faithfulness) so you do not hand-roll a rubric from scratch. You wrap the judge in a normal evaluator function and pass it to `evaluate` like any other.

### Custom judges with structured output

When the prebuilt rubrics do not fit, write your own judge — but make it return **structured output** so the score is parseable and the reasoning is captured:

```python
class Grade(BaseModel):
    score: float = Field(description="0.0 to 1.0")
    reasoning: str = Field(description="why this score")

def faithfulness_judge(inputs, outputs, reference_outputs) -> dict:
    grade = judge_model.with_structured_output(Grade).invoke(
        f"Context: {inputs['context']}\n"
        f"Answer: {outputs['answer']}\n"
        "Score how faithful the answer is to the context, 0-1, and explain."
    )
    return {"key": "faithfulness", "score": grade.score, "comment": grade.reasoning}
```

Structured output is not optional polish — parsing a free-text "I'd give this about an 8/10" is brittle and loses the reasoning. Forcing a schema gives you a clean numeric score *and* a rationale you can audit.

### Avoiding judge bias

LLM judges have well-documented failure modes. Design around them:

- **Position bias** — in pairwise grading, models favor whichever answer came first. Randomize order, or run both orders and average.
- **Verbosity / length bias** — judges reward longer answers regardless of quality. Instruct the rubric to ignore length, or normalize.
- **Self-preference** — a model tends to prefer its own outputs. Prefer a *different* model family for the judge than the one that generated the answer.
- **Leniency drift** — judges cluster scores near the top of the scale. Use a small discrete scale (pass/fail, or 1–3) rather than a fine-grained 0–100 that the model cannot actually resolve.
- **Sycophancy to the rubric** — vague rubrics let the judge rationalize any score. Make criteria concrete and give examples of each grade.

### Calibrating judges

A judge you have not validated is a random number generator with good vibes. Calibrate it:

1. Assemble a small set of examples with **human-assigned** ground-truth scores.
2. Run the judge over them and compare its scores to the human labels (agreement rate, correlation).
3. Iterate on the rubric until the judge agrees with humans often enough to trust.
4. Re-check periodically — if you change the judge model, re-calibrate.

The discipline: treat the judge as a system under test, evaluated against a human golden set, before you trust it to gate anything. A judge that agrees with humans 60% of the time is not measuring quality, it is adding noise.

## Why it matters

Evaluators are where "is this good?" becomes a number, and the *quality of that number* is entirely determined by the evaluator. A bad evaluator gives you false confidence — the worst possible outcome, because you ship regressions believing you tested them. Heuristics are trustworthy by construction; LLM judges are only trustworthy after calibration. Skipping calibration and then gating releases on an uncalibrated judge is measuring with a broken ruler and reading the number aloud with confidence.

Feedback keys matter because they are the through-line: the same `correctness` key flows from offline experiments (file 03) to online production evaluators (file 06) to human annotation (file 07). Consistent keys let you compare a dev experiment's correctness against production's correctness on the same axis.

## Pitfalls

- **LLM judge where a heuristic suffices.** Grading "is this valid JSON" with a model is slow, costly, and *less* reliable than `json.loads`. Escalate only for genuinely semantic properties.
- **Uncalibrated judges gating releases.** If you never checked the judge against humans, its scores are unvalidated. Calibrate before you trust.
- **Free-text judge output.** Parsing prose for a score is fragile. Force structured output.
- **Same model judging its own output.** Self-preference inflates the score. Use a different model for the judge.
- **Fine-grained scales the model cannot resolve.** A 0–100 judge produces noise dressed as precision. Prefer pass/fail or a 3-point scale.
- **Unstable feedback keys.** Renaming `correctness` to `accuracy` mid-project breaks your time series and comparison history. Pick names and keep them.

## Exercises

1. Write two heuristic evaluators — an exact-match and a JSON-validity check — and run them in an experiment. Confirm each shows as its own feedback-key column.
2. Use `openevals` `create_llm_as_judge` with `CORRECTNESS_PROMPT` as an evaluator on a small dataset. Read the judge's comment on one example.
3. Write a custom judge that returns structured output (`score` + `reasoning`) via a Pydantic schema, and explain why the structured form beats parsing free text.
4. Build a 10-example human-labeled calibration set, run your judge over it, and compute its agreement rate with the human labels. State whether you would trust it to gate a release.

## Further reading

- Evaluation concepts (evaluators): https://docs.langchain.com/langsmith/evaluation-concepts
- Code (heuristic) evaluators: https://docs.langchain.com/langsmith/code-evaluator-sdk
- LLM-as-judge evaluators: https://docs.langchain.com/langsmith/llm-as-judge
- openevals: https://github.com/langchain-ai/openevals
- Bind an evaluator to a dataset / feedback: https://docs.langchain.com/langsmith/bind-evaluator-to-dataset
