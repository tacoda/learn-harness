# 06 · Monitoring, Dashboards & Alerts

## Mental model

Offline evaluation (file 03) answers "is this change good enough to ship?" Monitoring answers a different question, continuously: "is production still healthy *right now*?" It is the online half of the eval split.

Three layers stack up over your production traces:

```
alerts        ← notify a human/webhook when a metric crosses a threshold
   │  watch
dashboards    ← charts of metrics over time (latency, cost, errors, feedback)
   │  aggregate
online evals  ← score live runs automatically, producing feedback to chart
   │  run over
traces        ← the raw production runs (file 01)
```

Everything here is derived from the traces you are already emitting. If tracing is wired up (file 01), monitoring is largely configuration, not new instrumentation.

## In depth

### Monitoring and dashboards

The **Monitoring** section shows key metrics for a tracing project over time; the **Dashboards** section lets you build and configure custom charts. The metrics that matter:

- **Trace / run count** — volume. Sudden drops mean an upstream outage; spikes mean load or a runaway loop.
- **Latency** — execution time, usually viewed at percentiles (p50/p95/p99). The tail is where users feel pain.
- **Error rate** — failed runs, as a count or a percentage of total.
- **Cost** — LLM spend, derived from token counts per run. This is how you catch a prompt change that quietly tripled context size.
- **Feedback scores** — aggregated feedback keys, both human (file 07) and from online evaluators.

You slice these by the tags and metadata you attached in file 01 — latency for premium users, cost per tenant, error rate for one feature. This is the direct payoff of attaching identifiers to traces: without them, every chart is a single undifferentiated line.

### Online evaluators

**Online evaluators** run automatically against production traffic as it arrives, attaching feedback to live runs. Because production has no reference outputs, online evaluators are reference-free — they rely on heuristics, safety checks, and reference-free LLM judges that score properties like relevance, toxicity, or format-validity of a single run (or a multi-turn thread).

You configure an online evaluator as a rule on a project: "for runs matching this filter, run this evaluator, sample at this rate." The feedback it produces flows into the same feedback keys as offline eval, so a `toxicity` score means the same thing in a dashboard as it did in an experiment. Sampling matters here — you rarely judge 100% of production traffic with an LLM because that doubles your model spend; you sample a representative slice.

### Alerts and automations

**Alerts** fire real-time notifications when a metric crosses a threshold. LangSmith supports threshold-based alerting across the primary metrics: **Run Count, Cost, Errors, Feedback Score, and Latency**, with the full range of comparison operators (`<`, `<=`, `>`, `>=`). Typical alerts:

- error rate `>` 2% over 5 minutes → page on-call;
- p99 latency `>` 10s → investigate the slow provider;
- cost `>` daily budget → someone shipped an expensive change;
- feedback score `<` threshold → quality regression in production;
- run count `<` expected floor → traffic stopped arriving (upstream dead).

Alerts deliver to destinations like PagerDuty or a webhook, so they plug into your existing incident tooling.

**Automations / rules** are the more general mechanism: a rule matches runs by filter and takes an action — run an online evaluator, add matching runs to a dataset, send them to an annotation queue (file 07), or trigger a webhook. Rules are how you build the production feedback loop without manual work: "sample 5% of low-feedback runs into the review queue" or "add every errored run to the `production-failures` dataset" becomes a standing rule instead of a cron job.

## Why it matters

An LLM system that passed every offline eval can still degrade in production: a provider gets slower, a model version shifts behind the API, input distribution drifts toward cases your dataset never covered, or a prompt change balloons cost. Offline eval cannot catch any of these because they happen *after* you shipped. Monitoring is the only thing watching while the system runs.

Alerts convert monitoring from something a human has to remember to look at into something that pages you when it matters. And automations close the loop back to the earlier files: production runs that score badly get routed into annotation queues and datasets, which improves the offline eval suite, which catches the next regression before it ships. Monitoring is not just a safety net — it is the intake pipe for your test data.

## Pitfalls

- **Watching only the average.** A healthy p50 hides a p99 that is timing out for 1% of users. Chart percentiles, not means, for latency.
- **No identifiers to slice by.** If you did not attach metadata in file 01, every dashboard is one aggregate line and you cannot tell *which* tenant or feature is on fire. Instrument first.
- **Judging 100% of traffic online.** Running an LLM judge on every production run can rival the cost of production itself. Sample.
- **Alert fatigue.** Thresholds set too tight page constantly and get muted, so the real incident is ignored. Tune thresholds against observed baselines and alert on sustained breaches, not single spikes.
- **Monitoring without automation.** If bad production runs are visible but never routed into datasets or queues, you see the problem and learn nothing from it. Wire rules to capture failures.
- **Cost blindness.** Not charting cost means a context-size regression is invisible until the invoice arrives. Put cost on a dashboard and alert on it.

## Exercises

1. Open the Monitoring view for a project with production traffic and identify the trace count, latency, error rate, and cost charts. Which metric would you alert on first for your app, and why?
2. Configure an online evaluator (a reference-free heuristic or safety check) to run on a sample of incoming traces, and confirm its feedback appears as a chartable score.
3. Create an alert on error rate or latency with a threshold and a destination. Describe what a good threshold is for your traffic and why single-spike alerting is a trap.
4. Design an automation rule that routes low-feedback production runs into an annotation queue or dataset, and explain how that closes the loop into your offline eval suite (files 02–04).

## Further reading

- Monitoring (observability tutorial): https://docs.langchain.com/langsmith/observability-llm-tutorial
- Dashboards: https://docs.langchain.com/langsmith/dashboards
- Alerts: https://docs.langchain.com/langsmith/alerts
- Online evaluations: https://docs.langchain.com/langsmith/online-evaluations
- Automations / rules: https://docs.langchain.com/langsmith/rules
