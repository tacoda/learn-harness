# 07 · Annotation Queues & Feedback

## Mental model

**Feedback** is the universal currency for "how good was this run?" It is a scored, keyed judgment attached to a run — and it comes from three sources that all land in the same place:

```
                  ┌── automated evaluators (files 03, 06)
feedback (run) ───┼── end users (thumbs up/down, ratings)
                  └── human reviewers (annotation queues)
```

Because all three produce feedback under the same keys, a `correctness` score means the same thing whether a judge, a user, or an expert produced it — and they aggregate on the same dashboards and drive the same automations.

An **annotation queue** is the structured workflow for the third source: human review. It is an inbox of runs flagged for a person to grade against a rubric. The point of a queue (versus ad-hoc clicking around traces) is process — defined criteria, required fields, permissions, and a clean path from "reviewed run" to "dataset example."

The loop this file is really about: production run → human (or user) feedback → corrected example → dataset → better offline eval. This is how a test suite grows from real quality signals instead of guesses.

## In depth

### The feedback API

Attach feedback to any run by its id:

```python
from langsmith import Client
client = Client()
client.create_feedback(run_id, key="user-score", score=1.0)
```

`create_feedback` takes a run id, a `key`, and a `score` (and optionally a `value`, `comment`, or correction). To attach feedback you need the run's id, which means capturing it when you trace. Generate one and pass it through `langsmith_extra`:

```python
from langsmith import traceable, Client, uuid7
from langsmith.wrappers import wrap_openai

client = wrap_openai(OpenAI())

@traceable
def support_bot(question: str) -> str:
    ...

run_id = str(uuid7())
support_bot("How many users on Starter?", langsmith_extra={"run_id": run_id})

# later — when the user clicks thumbs-up:
Client().create_feedback(run_id, key="user-score", score=1.0)
```

`uuid7` is time-ordered, which keeps run ids sortable. The pattern is: mint the id, pass it into the traced call, hold onto it (return it to the frontend), and when the user reacts, POST feedback against it. That is how a thumbs-up button in your UI becomes a `user-score` you can chart.

### Capturing user feedback in production

The production idiom: your API returns the `run_id` alongside the answer; the frontend renders the answer with feedback controls; when the user rates it, the frontend calls an endpoint that does `create_feedback(run_id, key="user-score", score=...)`. Now real user sentiment is a metric you can monitor (file 06), filter on, and — crucially — use to *find* the runs worth reviewing. Runs with a thumbs-down are the highest-value candidates for the annotation queue.

### Feedback configs

Before humans annotate, define what a feedback key *means* with a feedback config — continuous, categorical, or freeform:

```python
client.create_feedback_config(
    "accuracy",
    feedback_config={"type": "continuous", "min": 0, "max": 1},
    is_lower_score_better=False,
)
client.create_feedback_config(
    "correctness",
    feedback_config={"type": "categorical",
                     "categories": [{"value": 1, "label": "Pass"},
                                    {"value": 0, "label": "Fail"}]},
)
client.create_feedback_config("notes", feedback_config={"type": "freeform"})
```

The config constrains what annotators can enter (a slider, a set of choices, a text box), which keeps human scores consistent across reviewers.

### Annotation queues

A queue bundles runs for review and defines the rubric the reviewer sees:

```python
queue = client.create_annotation_queue(
    name="QA Review Queue",
    description="Review LLM outputs for accuracy",
    rubric_instructions="Score each response. Note anything unusual.",
    rubric_items=[
        {"feedback_key": "accuracy", "description": "How accurate?",
         "score_descriptions": {"0": "Wrong", "1": "Perfect"}, "is_required": True},
        {"feedback_key": "correctness", "description": "Pass or fail?",
         "value_descriptions": {"Pass": "Correct", "Fail": "Has errors"},
         "is_required": True},
        {"feedback_key": "notes", "is_required": False},
    ],
)
```

Each `rubric_item` references a feedback config by key and customizes how it appears in *this* queue. `is_required` forces the annotator to complete it before submitting; `rubric_instructions` is the guidance shown at the top of the interface. Runs get into a queue either manually ("add to queue" from a trace) or automatically via a rule (file 06) — e.g. "route all thumbs-down runs here."

### Closing the loop into datasets

This is the payoff. In the annotation interface a reviewer does not just score a run — they can **edit its inputs, outputs, and reference outputs** and add it to a dataset. Those modifications carry over to the dataset example along with metadata. So the reviewer sees a production run that got a thumbs-down, corrects the output to what it *should* have been, and pushes it into the golden dataset. The next experiment (file 03) now includes that case, and you can never silently regress on it again.

That is the whole arc of this track in one sentence: production trace → user feedback flags it → human reviewer corrects it → it becomes a dataset example → it gates future releases.

## Why it matters

Automated evaluators (files 03–04, 06) scale but are only as good as their rubrics and calibration. Human judgment is the ground truth those evaluators are calibrated *against*, and the only reliable source for subjective or high-stakes quality. Annotation queues make human review a repeatable process rather than a heroic one-off, with consistent rubrics so two reviewers grade the same way.

User feedback matters because it is the cheapest, most abundant, and most honest quality signal you have — it comes from the people the system actually serves. Capturing it turns every production interaction into potential training and test data. And the dataset loop matters because it is what makes the whole system *improve*: without it, you find bugs and fix them once; with it, every fix becomes a permanent regression guard.

## Pitfalls

- **Not capturing the run id.** If you do not mint and thread a `run_id` through the traced call, you have nowhere to attach user feedback later. Capture it at request time.
- **Inconsistent feedback keys across sources.** If users produce `user-score` but reviewers produce `human-score` and judges produce `correctness`, you cannot compare them. Standardize keys and configs.
- **No feedback config.** Free-for-all annotation (any reviewer enters any scale) produces unusable data. Define configs so scores are constrained and comparable.
- **Reviewing without correcting.** Scoring a bad run and moving on wastes the review. The value is in *fixing* the output and pushing it to the dataset — close the loop.
- **Queuing everything.** A queue with 10,000 unfiltered runs never gets reviewed. Route selectively — thumbs-down runs, low online-eval scores, errored runs — so reviewers see high-value cases.
- **Treating user thumbs-up as ground truth.** Users reward confident-sounding answers, not correct ones. User feedback is a signal to *investigate*, not a substitute for expert review on high-stakes cases.

## Exercises

1. Mint a `run_id` with `uuid7`, thread it through a traced call via `langsmith_extra`, and attach a `user-score` with `create_feedback`. Confirm the feedback shows on that run.
2. Create feedback configs for a continuous `accuracy` and a categorical `correctness`, then create an annotation queue with rubric items referencing them.
3. Add a production run to your queue, review it, correct its output, and push it into a dataset. Verify the corrected value is what appears in the dataset example.
4. Design the end-to-end loop for your app: which runs get user feedback, which of those get routed to the queue (and by what rule), and how reviewed runs feed the golden dataset. Name the pitfall you are most exposed to.

## Further reading

- Evaluation concepts (human feedback): https://docs.langchain.com/langsmith/evaluation-concepts
- Annotation queues (SDK): https://docs.langchain.com/langsmith/annotation-queues-sdk
- Annotation queues (UI): https://docs.langchain.com/langsmith/annotation-queues
- Feedback (capture user feedback): https://docs.langchain.com/langsmith/attach-user-feedback
- Add runs to a dataset: https://docs.langchain.com/langsmith/manage-datasets-in-application
