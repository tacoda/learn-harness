# 03 · Evaluation & Experiments

## Mental model

Evaluation in LangSmith is a single function call that ties together the three nouns from the previous files:

```
evaluate( target_fn , data=dataset , evaluators=[...] ) → experiment
```

- **target** — the thing under test. A function that takes one example's `inputs` and returns outputs.
- **data** — the dataset (or a filtered slice of it) to run against.
- **evaluators** — the graders that score each output (file 04).

The result is an **experiment**: one complete pass of the target over every example, with every output scored. An experiment is itself a set of traces, grouped and tagged, viewable and *comparable* in the UI. The whole discipline reduces to: run experiment A, change something, run experiment B, compare the score columns.

The frame to hold: an experiment is a row of numbers attached to a version of your system. Ship decisions are made by comparing rows, not by reading individual outputs.

## In depth

### The `evaluate` call

```python
from langsmith import Client
client = Client()

results = client.evaluate(
    target,                       # your target function
    data="Support QA",            # dataset name, dataset object, or list_examples(...)
    evaluators=[correctness, tone],
    experiment_prefix="gpt-5-nano",
    max_concurrency=4,
)
print(results.experiment_name)    # e.g. "gpt-5-nano-a1b2c3"
```

`client.evaluate(...)` (also importable top-level as `from langsmith import evaluate`) runs the target over the data, applies each evaluator to each result, and uploads everything as an experiment. Key arguments:

- **`data`** — a dataset name string, a dataset object, or the iterator returned by `client.list_examples(...)` (which lets you filter by split or version).
- **`experiment_prefix`** — a human-readable label; LangSmith appends a unique suffix so repeated runs do not collide.
- **`max_concurrency`** — how many examples to run in parallel. Turn this up to finish faster, down to respect provider rate limits.

### Target functions

A target function takes `inputs: dict` (one example's inputs) and returns a `dict` (the outputs to be scored):

```python
def target(inputs: dict) -> dict:
    response = openai_client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "Answer accurately."},
            {"role": "user", "content": inputs["question"]},
        ],
    )
    return {"answer": response.choices[0].message.content.strip()}
```

The contract: the keys you read from `inputs` must match your dataset's input schema, and the keys you return become the `outputs` your evaluators receive. The target can be anything — a raw provider call, a LangChain chain, a compiled LangGraph agent (`lambda inputs: agent.invoke(...)`), or a wrapper around your production endpoint. If the target is traced (it usually is), each example's run nests under the experiment.

### Evaluators (the short version)

An evaluator is a function `(inputs, outputs, reference_outputs) -> bool | float | dict`. It receives the example's inputs, your target's outputs, and the reference outputs from the dataset, and returns a score. File 04 covers writing them; here it is enough to know they run once per example and produce the per-row scores.

### Comparing experiments

The payoff is in the UI's comparison view. Run two experiments against the *same dataset* and LangSmith aligns them example-by-example, showing score deltas per evaluator and per example. This is how you answer "did switching from `gpt-5-nano` to `gpt-5-mini` actually help, and on which cases did it regress?" You are not eyeballing outputs — you are reading a diff of scores.

Because comparison is example-aligned, keep the dataset version fixed across the experiments you compare (`as_of` a version; see file 02). Comparing experiments run against different dataset versions is comparing apples to a different bag of apples.

### Summary evaluators

Ordinary evaluators score one example at a time. A **summary evaluator** scores the *whole experiment at once* — for metrics that only make sense in aggregate, like F1, precision/recall, or overall pass rate:

```python
def f1_summary(outputs: list[dict], reference_outputs: list[dict]) -> dict:
    # receives ALL outputs and ALL reference outputs for the experiment
    ...
    return {"key": "f1_score", "score": f1}
```

You pass summary evaluators via the `summary_evaluators` argument to `evaluate`. Use them for corpus-level metrics; use per-example evaluators for everything else.

### Pairwise / comparative evaluation

Sometimes there is no reference answer and "which of these two is better" is the only tractable question. **Pairwise evaluation** scores the outputs of two (or more) *existing experiments* against each other rather than against a gold label:

```python
from langsmith import evaluate

# Compare two experiments you already ran:
evaluate(
    ("experiment-a", "experiment-b"),   # existing experiment names
    evaluators=[pairwise_judge],        # judge picks a winner per example
)
```

For more than two experiments, use `evaluate_comparative()`. Pairwise is the natural fit for open-ended generation (summaries, tweets, chat replies) where absolute correctness is undefined but relative quality is judgeable.

### Offline vs. online evaluation

- **Offline** — everything above. You run a target over a fixed dataset, on demand, in development or CI. Reference outputs are usually available. This is the release-gating workhorse.
- **Online** — evaluators run automatically against live production traffic as it arrives (file 06). No reference outputs exist, so online evaluators are reference-free: heuristics, safety checks, LLM judges scoring properties like relevance or toxicity. Offline answers "is this change good enough to ship"; online answers "is production still healthy right now."

## Why it matters

Experiments turn "I think the new prompt is better" into a defensible claim with a number and a diff. That is the difference between shipping on evidence and shipping on hope. The comparison view in particular is where you catch the regression that a summary score hides — the overall correctness went up two points, but the ten examples about billing all got worse, and the comparison view is the only place that shows.

The offline/online split matters because they answer different questions with different tools. Teams that only do offline eval ship confidently and then fly blind in production; teams that only do online monitoring catch fires but cannot safely make changes.

## Pitfalls

- **Comparing across dataset versions.** If the dataset changed between experiment A and B, the score delta conflates your code change with the data change. Pin the version.
- **Target function schema drift.** If the target reads `inputs["query"]` but the dataset stores `inputs["question"]`, every example errors. Keep the target's expected keys in lockstep with the dataset schema.
- **`max_concurrency` too high.** Cranking concurrency past your provider's rate limit produces a wall of 429 errors and a garbage experiment. Tune it to your quota.
- **Chasing the aggregate.** A single headline number can improve while an important subset regresses. Always open the comparison view and scan per-example deltas before declaring victory.
- **Using pairwise when you have references.** If you have gold answers, absolute scoring is more informative than "A beat B." Reserve pairwise for genuinely open-ended tasks.

## Exercises

1. Write a target function and run `client.evaluate` against a 5-example dataset with one evaluator and `experiment_prefix="v1"`. Note the returned `experiment_name`.
2. Change the model (or prompt), run again as `v2`, and open the two experiments in the comparison view. Identify one example where the score changed and read both outputs.
3. Add a summary evaluator that reports overall pass rate, and confirm it shows as a single experiment-level score rather than per example.
4. Explain when you would reach for pairwise evaluation instead of a reference-based evaluator, and why online evaluators cannot use `reference_outputs`.

## Further reading

- Evaluation quickstart: https://docs.langchain.com/langsmith/evaluation-quickstart
- Evaluation concepts: https://docs.langchain.com/langsmith/evaluation-concepts
- Compare experiment results: https://docs.langchain.com/langsmith/compare-experiment-results
- Summary evaluators: https://docs.langchain.com/langsmith/summary
- Pairwise evaluation: https://docs.langchain.com/langsmith/evaluate-pairwise
