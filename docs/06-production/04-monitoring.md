# 04 · Monitoring

## Mental model

Offline evaluation (file 05, `docs/03-langsmith/03-evaluation-and-experiments.md`) answers "is this change good enough to ship?" **Monitoring answers a different question, continuously: "is production healthy *right now*?"** It is the online half of the loop from file 01, and it is almost entirely derived from the traces your deployed agent already emits.

Four layers stack over your production traces, and the pattern is that each layer only exists because the one below it does:

```
   alerts        ← page a human / hit a webhook when a metric crosses a line
      │  watch
   dashboards    ← metrics over time: latency, cost, errors, volume, feedback
      │  aggregate
   online evals  ← score live runs automatically → feedback you can chart
      │  run over
   traces        ← the raw production runs (emitted by the deployment)
```

If tracing is wired (file 02, `docs/03-langsmith/01-tracing-and-observability.md`), monitoring is **configuration, not new instrumentation**. The reusable move: you do not instrument for monitoring; you instrument once for tracing, then derive every dashboard and alert from those traces. That is why monitoring a complex multi-agent system is the same work as monitoring `support-triage` — more spans per trace, identical pipeline.

## In depth

### Wiring LangSmith in production

A deployed Agent Server emits traces to LangSmith when the environment carries the tracing config. Set these per-environment (file 03), not in code:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls-...
LANGSMITH_PROJECT=support-triage-prod     # separate project per environment
```

Two decisions that pay off later, both from `docs/03-langsmith/01-tracing-and-observability.md`:

- **One project per environment.** `support-triage-prod` and `support-triage-staging` trace to different projects so staging noise never pollutes prod metrics.
- **Attach identifiers to every run** — `user_id`, `tenant`, `feature`, a release/version tag — as metadata and tags. Without them every dashboard is one undifferentiated line and you cannot tell *which* tenant is on fire. This is the single highest-leverage instrumentation habit, and it is what makes the `group by` in every chart below useful.

### Dashboards and the core metrics

LangSmith auto-creates a **prebuilt dashboard** per tracing project (trace count, error rate, token usage, latency). You add **custom dashboards** for what your app cares about; chart templates include *Error rate over time*, *Average latency by model*, *Run volume*, *Token usage over time*, and *Most expensive models*.

The metrics that matter, and how to read each:

- **Run / trace volume** — throughput. A sudden drop means an upstream outage (traffic stopped arriving); a spike means load or a runaway loop.
- **Latency — at percentiles, not the mean.** Chart **p50** (typical experience) *and* **p99** (the tail where users actually feel pain). A healthy p50 routinely hides a p99 that is timing out for 1% of users. For agents the tail is dominated by tool calls and multi-step loops, so also break latency out by model and by node.
- **Cost / tokens per run** — LLM spend, derived from token counts. This is how you catch a prompt change that quietly tripled context size before the invoice does.
- **Error rate** — failed runs as a count and a percentage. Break out by error type.
- **Feedback scores** — aggregated feedback keys, both human (`docs/03-langsmith/07-annotation-queues-and-feedback.md`) and from online evaluators below.

Slice every one of these by the metadata you attached: p99 latency for premium users, cost per tenant, error rate for one feature. That slicing is the entire payoff of instrumenting identifiers.

### Online / automated evaluators on live traces

Production has no reference outputs, so online evaluators are **reference-free**: heuristics, safety checks, and reference-free LLM-as-judge scorers that grade a single live run (or a whole thread) on properties like relevance, toxicity, or format-validity. You configure one as a **rule** on a project — "for runs matching this filter, run this evaluator, at this sample rate" — from the Observability tab. The feedback it produces flows into the *same feedback keys* as offline eval, so a `helpfulness` score means the same thing on a dashboard as it did in an experiment.

For `support-triage`, a useful online evaluator: "did the reply either resolve the issue or correctly escalate?" scored by a judge on a sample of live runs, charted as a `resolution_quality` feedback score and alerted on when it drops.

One cost caveat straight from the docs: when an online evaluator runs on a trace, that trace is **auto-upgraded to extended data retention**, which affects trace pricing. That is usually a feature (you keep the traces most worth investigating) but it is a real cost lever — another reason to sample rather than judge everything.

### Trace sampling at volume

At low volume, trace and judge everything. At high volume, both become expensive — trace storage and, especially, LLM-judge spend that can rival production cost itself. Two independent sampling knobs:

- **Trace sampling** — capture a representative fraction of runs rather than 100%. Keep errored runs at full sampling (you always want those) and downsample the boring successful bulk.
- **Online-eval sampling** — the sample rate on the evaluator rule. You rarely judge 100% of traffic with an LLM; a representative slice tracks the trend at a fraction of the cost.

The generalisable rule: **sample the routine, keep the exceptional.** Full fidelity on errors and low-feedback runs; a sampled slice of the happy path. This scales down cost without blinding you to the failures that matter — and it matters more, not less, as the system grows.

### Alerts and automation rules

**Alerts** fire real-time notifications when a project metric crosses a threshold. LangSmith alerts are project-scoped and cover **Run Count, Cost, Errors, Feedback Score, and Latency**, with comparison operators (`<`, `<=`, `>`, `>=`), and route to **Slack, PagerDuty, Dynatrace, or any webhook**. You can preview a threshold against a historical window to see how often it *would* have fired — use that to avoid a noisy alert.

A starting alert set for `support-triage-prod`:

| Alert | Why |
|---|---|
| error rate `>` 2% over 5 min | shipped a bad change / provider failing |
| p99 latency `>` 10s | a slow provider or a runaway loop |
| cost `>` daily budget | a prompt change ballooned context |
| feedback score `<` threshold | quality regression users are feeling |
| run count `<` expected floor | traffic stopped — upstream is dead |

**Automation rules** are the more general mechanism: a rule matches runs by filter and takes an action — run an online evaluator, **add matching runs to a dataset**, send them to an annotation queue, or hit a webhook. Rules are how you build the feedback loop without manual work: "add every errored run to the `production-failures` dataset" or "sample 5% of low-feedback runs into the review queue" becomes a standing rule. This is the literal wiring of the `feedback → build` arrow from file 01, and it is the subject of file 05.

### What to alert on vs. what to watch

Not every metric deserves a page. The discipline:

- **Alert** (wake a human) on things that mean users are being hurt *now* and someone must act: error-rate spikes, p99 blowouts, traffic flatlines, budget breaches.
- **Watch** (dashboard, review regularly) on trends that inform decisions but are not emergencies: token-cost creep, feedback drift, per-tenant latency, model mix.

Tune alert thresholds against observed baselines and fire on **sustained** breaches, not single spikes — the fastest way to make alerting useless is alert fatigue, where every threshold pages constantly and the real incident gets muted with the noise.

## Why it matters

An agent that passed every offline eval can still degrade in production in ways offline eval structurally cannot catch, because they happen *after* you shipped: a provider gets slower, a model version shifts behind the API, input distribution drifts toward cases your dataset never covered, or a prompt change balloons cost. Monitoring is the only thing watching while the system runs, and alerts convert it from "something a human remembers to check" into "something that pages you when it matters." Just as important, automation rules make monitoring the **intake pipe for your test data** — bad production runs get routed into datasets that improve the offline suite that catches the *next* regression before it ships. Monitoring is not a safety net bolted on at the end; it is the sensor half of the improvement loop, and it is the same sensor whether the trace has three spans or three hundred.

## Pitfalls

- **Watching only the average.** A healthy p50 masks a p99 that is timing out for 1% of users. Chart percentiles for latency, always.
- **No identifiers to slice by.** If you did not attach metadata in tracing, every dashboard is one aggregate line and you cannot localise an incident. Instrument identifiers first (file 02).
- **Judging 100% of traffic online.** An LLM judge on every run can rival production cost, and online evals auto-upgrade trace retention. Sample.
- **Alert fatigue.** Thresholds set too tight page constantly, get muted, and hide the real incident. Baseline your thresholds and alert on sustained breaches; preview against history before enabling.
- **Monitoring without automation.** Bad runs that are visible but never routed into a dataset or queue teach you nothing. Wire rules to capture failures — that is the loop, not decoration.
- **Cost blindness.** Not charting cost means a context-size regression is invisible until billing. Put cost on a dashboard and alert on it (`docs/05-expert/07-cost-and-latency-optimization.md`).
- **Mixing environments in one project.** Staging traffic in the prod project corrupts every metric and alert. One project per environment.

## Exercises

1. Open the prebuilt dashboard for a project with real (or replayed) traffic and locate run volume, latency (with percentiles), error rate, and cost. Which one would you alert on first for your app, and why?
2. Add p50 and p99 latency to a custom dashboard and grouped by model. Find a case where p50 looks fine but p99 does not, and explain what a mean would have hidden.
3. Configure an online evaluator (a reference-free judge or safety check) on a *sample* of incoming traces and confirm its feedback appears as a chartable score. Note the retention/cost implication.
4. Create one alert (error rate or latency) with a threshold and a destination, previewing it against history first. Then write one automation rule that routes low-feedback or errored runs into a dataset, and explain how that closes the loop into file 05.

## Further reading

- Observability quickstart (tracing in prod): https://docs.langchain.com/langsmith/observability-quickstart
- Dashboards: https://docs.langchain.com/langsmith/dashboards
- Alerts: https://docs.langchain.com/langsmith/alerts
- Online evaluations (LLM-as-judge on live traces): https://docs.langchain.com/langsmith/online-evaluations
- Evaluation concepts (offline vs online): https://docs.langchain.com/langsmith/evaluation-concepts
- Sibling: `docs/03-langsmith/06-monitoring-dashboards-alerts.md`, `docs/03-langsmith/01-tracing-and-observability.md`, `docs/05-expert/07-cost-and-latency-optimization.md`
