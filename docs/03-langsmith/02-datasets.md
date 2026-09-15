# 02 · Datasets

## Mental model

A **dataset** is a named, versioned collection of **examples**. An example is an input paired (optionally) with a reference output — the "right answer" you want to hold your system to:

```
example = {
  "inputs":  {"question": "What is LangSmith?"},   # what goes into your system
  "outputs": {"answer": "An observability + eval platform."}  # the reference / gold answer
}
```

The mental frame: a dataset is a *test suite for a non-deterministic system*. Where unit tests assert exact equality, an eval dataset pairs inputs with reference outputs and lets graded evaluators (file 04) decide how close you got. The dataset is the fixed thing you evaluate *against*; experiments (file 03) are the runs *over* it.

Two kinds of dataset dominate in practice:

- **Golden datasets** — small, hand-curated, high-confidence examples that encode "this is unambiguously correct." These gate releases.
- **Production-derived datasets** — examples harvested from real traces, capturing the messy distribution your system actually faces.

You want both. Golden data catches regressions on cases you *know* matter; production data keeps your test set honest about the inputs users actually send.

## In depth

### Creating a dataset and examples

```python
from langsmith import Client
client = Client()

dataset = client.create_dataset(
    dataset_name="Support QA",
    description="Golden questions for the support bot",
)

client.create_examples(
    dataset_id=dataset.id,
    examples=[
        {"inputs": {"question": "How many users on Starter?"},
         "outputs": {"answer": "5"}},
        {"inputs": {"question": "How do I reset my password?"},
         "outputs": {"answer": "Click 'Forgot password' on the login page."}},
    ],
)
```

`create_examples` takes a list of dicts, each with `inputs` and (optionally) `outputs`. Examples without a reference output are legal — you use those when your evaluators are reference-free (heuristics, safety checks) or when a human will supply the judgment later. Use `client.has_dataset(dataset_name=...)` to make dataset creation idempotent in scripts:

```python
if not client.has_dataset(dataset_name="Support QA"):
    dataset = client.create_dataset(dataset_name="Support QA")
    client.create_examples(dataset_id=dataset.id, examples=[...])
```

### Schema

Examples are dicts, and the *shape* of `inputs` and `outputs` is your contract. Your target function (file 03) receives `inputs` verbatim and must read the keys you put here; your evaluators receive `reference_outputs` with the `outputs` keys. Pick a schema early and keep it stable across every example in the dataset — a target function cannot branch on "sometimes there's a `question` key, sometimes a `text` key." LangSmith can enforce this: datasets support an optional JSON schema for inputs and outputs so that malformed examples are rejected at creation time.

### Building datasets from traces (production → dataset)

This is the highest-leverage path. Once you are tracing production (file 01), every interesting run is a candidate example:

- **From the UI:** open a trace, click "Add to dataset," and adjust the inputs/reference outputs before saving. You can correct the output to what it *should* have been — that edited value becomes the reference.
- **Via annotation queues** (file 07): route runs to human reviewers who fix inputs/outputs, then push the corrected examples into a dataset. Modifications made in the queue carry over.
- **Programmatically:** pull runs with `client.runs.query` (or the deprecated `client.list_runs`; see file 01), map each run's `inputs`/`outputs` into example dicts, and `create_examples`. Filter to root runs — `is_root=True` — so you import whole requests rather than every nested child span.

The workflow that matters: a user reports a bad answer → you find the trace → you add it to the dataset with the *correct* reference output → your next experiment now includes that case → you never regress on it again. That loop is how an eval suite grows to reflect reality instead of your imagination.

### Splits

A **split** is a named subset of a dataset — commonly `train`, `test`, `validation`, or domain-specific slices like `edge-cases`. Splits let you evaluate on a slice without maintaining separate datasets:

```python
from langsmith import evaluate

results = evaluate(
    my_target,
    data=client.list_examples(dataset_name="Support QA", splits=["test"]),
    evaluators=[correct],
    experiment_prefix="support-qa",
)
```

You assign examples to splits in the UI or via the SDK. Use splits to keep a held-out set the model has never been tuned against, or to isolate a category of hard cases you track separately.

### Versions

Datasets are **versioned automatically** — every modification (adding, editing, deleting examples) creates a new version, and you can tag versions (e.g. `latest`, or a named tag) and pin an evaluation to a specific one:

```python
results = evaluate(
    my_target,
    data=client.list_examples(dataset_name="Support QA", as_of="latest"),
    evaluators=[correct],
)
```

`as_of` accepts `"latest"`, a tag, or a timestamp. This is what makes eval reproducible: an experiment run against version X can be re-run against the exact same X months later, so a score change reflects a code change and not a dataset that shifted underneath you.

## Why it matters

You cannot improve what you cannot measure, and you cannot measure an LLM system without a dataset. "It seems better" is not a release criterion; "correctness went from 0.71 to 0.86 on the 200-example golden set, version 12" is. The dataset is the artifact that converts vibes into a number.

Versioning and splits matter because eval results are only trustworthy if the thing you measured against is stable and named. An unversioned dataset that someone edited between two experiments makes the comparison meaningless.

## Pitfalls

- **Inconsistent example schema.** If example A has `inputs.question` and example B has `inputs.text`, your target function breaks halfway through the run. Standardize the schema and consider attaching a JSON schema to enforce it.
- **Only golden data.** Hand-written examples reflect what you *think* users ask. Without production-derived examples your eval set drifts away from reality and your scores stop predicting real quality.
- **Editing datasets mid-comparison.** Changing examples between two experiments invalidates the comparison. Pin `as_of` a version when you need apples-to-apples.
- **Reference outputs that are too rigid.** Storing one exact string as the reference forces exact-match grading. If the task has many valid answers, either store what a *graded* evaluator can judge or use a reference-free evaluator.
- **Dumping every trace in.** A dataset of 50,000 unfiltered production runs is expensive to evaluate and mostly redundant. Curate: sample, dedupe, and prioritize cases that were wrong or novel.

## Exercises

1. Create a dataset of 5 examples with a consistent `{"question": ...} → {"answer": ...}` schema, then add a 6th example programmatically and confirm a new version was created.
2. Take a trace from file 01, add it to a dataset from the UI, and edit the reference output to the answer you actually wanted. Explain why the *edited* value is what future experiments grade against.
3. Assign 2 of your examples to a `test` split and 3 to `train`, then run `list_examples` filtered to only the `test` split.
4. Describe the production → dataset loop in your own words, and name one filter you would apply before importing runs so you do not import noise.

## Further reading

- Manage datasets (SDK): https://docs.langchain.com/langsmith/manage-datasets
- Manage datasets in the application: https://docs.langchain.com/langsmith/manage-datasets-in-application
- Dataset versions: https://docs.langchain.com/langsmith/version-datasets
- Evaluation concepts (datasets): https://docs.langchain.com/langsmith/evaluation-concepts
