# 05 · Maintenance & Iteration

## Mental model

Files 02–04 got the agent packaged, deployed, and observed. This file is the arrow that makes it all a *loop* instead of a line: **production reality flows back into the next version.** Maintenance is not firefighting — it is a standing pipeline that turns what happened in prod into what ships next.

```
   ①  production      ②  build a          ③  regression eval     ④  ship a change
      feedback   ──▶     dataset from  ──▶    as a deploy gate ──▶   (canary via
      (traces,           real traces          (CI, before             assistant
       scores)                                 promotion)              versions)
                                                                          │
        ▲                                                                 │ if bad
        └──────────────  ⑥ debug from traces  ◀── ⑤ monitor ◀────────────┘ rollback
                          / detect drift          (file 04)
```

The reusable idea: every stage produces the input to the next, and the exceptional cases in prod (errors, low feedback) are the *raw material*, not a nuisance. A team without this loop tunes prompts on vibes and discovers regressions from users. A team with it ships changes that are gated by real failures and reversible in one call. The loop is identical for `support-triage` and for a multi-agent system — there are just more places to capture a failure.

## In depth

### ① Capture production feedback

Feedback is the signal that a run was good or bad. Three sources, all landing in the same LangSmith feedback keys (file 04, `docs/03-langsmith/07-annotation-queues-and-feedback.md`):

- **Explicit human feedback** — thumbs up/down, a rating, a correction — attached to a run via the API from your product UI.
- **Implicit signals** — did the user retry, escalate, abandon? Log these as feedback too.
- **Online-evaluator scores** — the reference-free judges from file 04 scoring live runs automatically.

For `support-triage`, capture a `resolved` thumbs signal from the support UI and a `resolution_quality` online-judge score. Together they tell you *which* runs to learn from.

### ② Build datasets from real traces

This is the highest-leverage habit in the whole track: **your best test cases are real production failures.** Instead of inventing examples, harvest them.

- **Automation rules** (file 04) do this hands-free: "add every errored run to the `triage-failures` dataset," "add every run with `resolved=false` to `triage-misses`." The rule runs standing, so the dataset grows itself.
- **Annotation queues** let a human review borderline runs, correct the output, and add the corrected example — turning a bad run into a labelled test case with a reference output.

The result is a dataset that mirrors what production actually throws at you, versioned so you can pin CI to a known set (`docs/03-langsmith/02-datasets.md`). Datasets support **splits** (e.g. keep exploratory cases isolated until you promote them into the main eval set) and **tagged versions** you can target in CI so dataset edits don't silently change what a gate means. The generalisation: the dataset is a living asset fed by monitoring, not a one-time fixture.

### ③ Regression eval as a deploy gate (CI)

Before any change is promoted, run the offline eval suite against the dataset and **block promotion on a regression.** This is the gate on the `staging → prod` arrow from file 01, and it is what makes evaluation *drive* development rather than decorate it (`docs/05-expert/08-evaluation-driven-development.md`, `docs/03-langsmith/08-testing-in-ci-cd.md`).

```python
# CI step: evaluate the candidate against the production-derived dataset
from langsmith import Client, aevaluate

results = await aevaluate(
    candidate_agent,                       # the new graph or assistant config
    data="triage-failures",                # dataset harvested from prod (pin a version)
    evaluators=[resolves_or_escalates, no_hallucinated_order, tone_ok],
    experiment_prefix="triage-pr-1421",
)
# fail the build if aggregate score regresses vs the current prod baseline
```

The pattern that scales: the gate compares the candidate to the **current production baseline**, not to an absolute number, so "did this change make things worse?" is the question CI answers on every PR. A regression stops the merge; only green changes reach staging, and only green-in-staging changes reach prod.

### ④ Prompt versioning

Most agent changes are prompt changes, and prompts deserve the same version control as code. LangSmith's prompt hub versions every saved prompt as a **commit**, and you **tag** commits (`prod`, `candidate`) to mark which is live (`docs/03-langsmith/05-prompt-management-and-hub.md`). The agent pulls the prompt by tag at runtime, so promoting a new prompt is moving a tag — and rolling back is moving it back. Prompts can carry their model config too. This keeps prompt iteration auditable (who changed what, when) and reversible, and it is what lets a non-engineer tune behaviour safely inside the eval gate.

### ⑤ Canary / staged rollout via assistant versions

Here is where the assistant-versioning of files 02–03 becomes the rollout mechanism. A config change (new prompt, model, or tool set) is a **new assistant version** — no code deploy. Roll it out in stages:

1. Create the new version (assistant `update` → new version).
2. Route a **small slice** of traffic to it (the canary) — e.g. 5% by pointing some clients at the new assistant ID while the rest stay on the current one.
3. Watch the canary's metrics and online-eval scores against the incumbent (file 04) on the *same* dashboards.
4. If healthy, shift traffic fully; if not, **roll back by re-pointing to the previous version.**

```python
candidate = await client.assistants.update(
    assistant_id, context={"system_prompt": NEW_PROMPT})   # new version
# route ~5% of runs to `candidate.version`, rest to the current prod version,
# compare feedback/latency/cost, then promote or revert.
```

The generalisable rule: **stage every change and compare against the incumbent on real traffic.** Canary is cheap here because a version is data, not an image — which is exactly why you prefer version bumps over redeploys.

### Rollback

Rollback is the property everything above is designed to protect. Two flavours, matching file 03:

- **Config rollback** — re-point the assistant to its previous version. One API call, zero downtime, no build. This covers the large majority of "the change is bad" moments.
- **Code rollback** — redeploy the previous graph revision. Slower (a rolling update), but in-flight threads survive because state is in Postgres.

The discipline: **know your rollback path before you ship, and make config the default path** because it is the fast one. A change you cannot cleanly reverse is a change you should not ship.

### ⑥ Debugging incidents from traces, and detecting drift

- **Incident debugging** — when an alert fires (file 04), the trace *is* the debugger. Open the offending runs, read the exact inputs, tool calls, and intermediate state span by span, and reproduce. **Time travel** (`docs/02-langgraph/11-durable-execution-and-time-travel.md`) lets you rewind a thread to the checkpoint before it went wrong, edit state, and replay a fix. Add the reproducing run to a dataset (② again) so the fix is gated forever after.
- **Drift detection** — the slow failure mode monitoring exists to catch. Watch for input distribution shifting toward cases your dataset never covered, a hosted model's behaviour changing behind a stable API, or feedback scores trending down while error rate stays flat. Drift rarely trips a hard threshold; you catch it by *watching* trends (file 04) and by periodically re-running the eval suite against a fresh sample of recent production traffic. When drift appears, the response is to feed the new cases back into the dataset (②) — closing the loop again.

## Why it matters

The difference between an agent that improves and one that decays is entirely this loop. Models drift, inputs drift, and dependencies change underneath you; a static agent gets worse over time even with zero code changes. The maintenance loop converts that entropy into a signal: production failures become datasets, datasets become gates, gates block regressions, and versioned config makes every fix reversible. It also collapses the cost of change — because most iteration is a prompt commit or an assistant version rather than a redeploy, you can ship fixes in minutes and undo them in seconds, which is what makes it *safe* to iterate quickly on a live system. On a complex multi-agent system this loop is not optional flourish; it is the only thing that keeps a large, drifting surface trustworthy, and it is the same loop you rehearsed on `support-triage`.

## Pitfalls

- **Datasets you write by hand instead of harvest.** Invented examples miss the cases production actually breaks on. Route real failures into datasets with automation rules — that is where the coverage is.
- **An advisory gate.** A regression check nobody blocks a merge on is a report, not a gate. Fail the build on regression, or it will not hold under deadline pressure.
- **Comparing to an absolute score, not the baseline.** "Above 0.8" hides a change that dropped you from 0.95 to 0.81. Gate on *regression vs current prod*.
- **Shipping without a rollback path.** Decide the reversal before you deploy, and default to config rollback (re-point the assistant version) because it is instant. An irreversible change is a liability.
- **Canary without comparison.** Sending 5% to a new version but not comparing its metrics against the incumbent is just a partial deploy. Watch both on the same dashboards.
- **Pinning CI to a moving dataset.** If the dataset changes underneath the gate, a "regression" may just be new examples. Target a tagged dataset version in CI.
- **Ignoring drift because nothing alerted.** Drift is a trend, not a spike. Re-run eval against fresh production samples periodically; do not wait for a threshold to trip.

## Exercises

1. Write an automation rule that adds every errored (or low-feedback) `support-triage` run to a `triage-failures` dataset. Let it run, then inspect the harvested examples — how many would you never have thought to write by hand?
2. Build a CI step that evaluates a candidate against that dataset and fails on a regression versus the current prod baseline. Deliberately introduce a prompt that regresses one case and confirm the gate blocks it.
3. Ship a config change to `support-triage` as a new assistant version, canary ~5% of traffic, compare its feedback/latency/cost to the incumbent, then either promote or roll back. Time the rollback.
4. Take a real incident (or simulate one): find the failing run from an alert, use time travel to rewind and replay a fix, and add the reproducing case to your dataset. Explain how this single workflow closes the loop from file 01.

## Further reading

- Evaluation concepts (regression, backtesting, splits, versions): https://docs.langchain.com/langsmith/evaluation-concepts
- Online evaluations & automation rules: https://docs.langchain.com/langsmith/online-evaluations
- Prompt engineering / versioning (commits, tags): https://docs.langchain.com/langsmith/prompt-engineering-concepts
- Manage assistants (versions, rollback): https://docs.langchain.com/langsmith/configuration-cloud
- Sibling: `docs/03-langsmith/08-testing-in-ci-cd.md`, `docs/03-langsmith/02-datasets.md`, `docs/03-langsmith/05-prompt-management-and-hub.md`, `docs/05-expert/08-evaluation-driven-development.md`, `docs/02-langgraph/11-durable-execution-and-time-travel.md`
