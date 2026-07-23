# 06 · The Production Pattern — Checklist & Decision Tree

## Mental model

This file is the whole track compressed into something you can apply to *any* future agent — a one-node `create_agent` or a twelve-agent supervisor system — without re-reading the other five files. The claim the track has been building toward:

> **Production readiness is a fixed set of concerns, each mapped to a specific LangGraph or LangSmith feature. The concerns don't change with agent complexity; only the amount inside each box does.**

So the pattern is: walk the concerns, wire each to its feature, run the loop. You learned it on `support-triage`. Applying it to a complex system is the same walk with bigger boxes.

```
   PACKAGE ──▶ DEPLOY ──▶ OBSERVE ──▶ EVALUATE ──▶ ITERATE ──┐
      │          │          │           │            │        │
   manifest   Agent      traces +    datasets     versions    │
   +assistant Server     dashboards  + gates      + canary    │
      ▲          Postgres  + alerts                            │
      └────────────────── feedback from prod ──────────────────┘
```

## In depth

### The concern → feature map (the reusable core)

This table *is* the pattern. For any new agent, go down the left column and wire the right column. Nothing here is `support-triage`-specific.

| Production concern | The question it answers | LangGraph / LangSmith feature | File |
|---|---|---|---|
| **Packaging** | How does a graph become a deployable unit? | `langgraph.json` manifest exporting a compiled graph | 02 |
| **Config vs code** | How do I tune behaviour without a redeploy? | Assistants (versioned graph configs) | 02, 03 |
| **Client contract** | What do callers depend on? | Threads & Runs API | 02 |
| **Secrets / config** | Where do keys and settings live? | `env` (local) + deployment secret store | 02, 03 |
| **Where it runs** | Cloud vs my infra? | Deployment option: Cloud / Hybrid / Self-hosted / Standalone | 03 |
| **Durability** | Does a crash lose work? | Postgres checkpointer (never `InMemorySaver` in prod) | 03 |
| **Scaling** | How do I handle concurrency? | Stateless workers + shared checkpoint store; split/distributed runtime | 03 |
| **Environments** | Where do I test safely? | Staging + prod deployments from one manifest | 03 |
| **Zero-downtime change** | How do I ship without an outage? | Rolling revisions (code) / new assistant version (config) | 03, 05 |
| **Observability** | Can I see production? | LangSmith tracing (one project per env, metadata on every run) | 04 |
| **Health metrics** | Is it healthy now? | Dashboards: volume, latency p50/p99, cost/tokens, errors, feedback | 04 |
| **Automated quality** | Is live output good? | Online (reference-free) evaluators on sampled traces | 04 |
| **Getting paged** | Who's told when it breaks? | Alerts (run count, cost, errors, feedback, latency → Slack/PagerDuty/webhook) | 04 |
| **Volume control** | How do I not go broke tracing? | Trace + online-eval sampling (keep exceptional, sample routine) | 04 |
| **Feedback capture** | How do I know what failed? | Feedback keys (human + implicit + online judges) | 05 |
| **Test data** | Where do test cases come from? | Datasets harvested from real traces via automation rules | 05 |
| **Regression gate** | How do I not ship a regression? | Offline eval in CI, blocking promotion, vs prod baseline | 05 |
| **Prompt control** | How do I version prompts? | Prompt hub commits + tags | 05 |
| **Safe rollout** | How do I de-risk a change? | Canary via assistant versions, compare to incumbent | 05 |
| **Rollback** | How do I undo fast? | Re-point assistant version (config) / redeploy prior revision (code) | 03, 05 |
| **Incident debugging** | Why did this run fail? | Traces + time travel (rewind/edit/replay) | 05 |
| **Drift** | Is it decaying silently? | Watch trends + periodic re-eval on fresh prod samples | 05 |

If you can name the feature for each row on your app, it is production-ready. If a row is blank, that is your next task.

### The go-live checklist

Before an agent takes real traffic:

- [ ] Graph exports a **compiled** object from `langgraph.json`; no `InMemorySaver` baked in.
- [ ] Secrets in the deployment secret store, nothing committed or hardcoded.
- [ ] Deployment option chosen against a real data-residency requirement (default: Cloud).
- [ ] **Postgres** persistence confirmed — kill the server mid-run, confirm resume.
- [ ] **Staging** deployment exists from the same manifest, with its own DB and keys.
- [ ] Tracing on, **one project per environment**, `user_id`/`tenant`/`feature`/version on every run.
- [ ] Dashboard with volume, latency **p50 and p99**, cost, error rate, feedback.
- [ ] Alerts on error rate, p99 latency, cost budget, and a run-count floor, routed to on-call.
- [ ] A **dataset** exists (seeded from staging/replayed traffic) and a **CI eval gate** blocks regressions vs the prod baseline.
- [ ] Automation rule routing errored / low-feedback runs into that dataset.
- [ ] Prompts versioned in the hub, pulled by tag.
- [ ] **Rollback path decided and rehearsed** — default to assistant-version re-point.

### The decision tree

Use this to make the recurring choices without re-deriving them each time.

**Where do I deploy?**
```
Compliance/residency forces data into my infra?
 ├─ no  → Cloud (SaaS)                    ← default; managed, autoscaling, GitHub CI/CD
 └─ yes → Must the control plane also be mine / air-gapped?
          ├─ no  → Hybrid                 ← my VPC for agents, managed control plane
          └─ yes → Self-hosted            ← I run everything
   (Just want the runtime, no control plane, own DBs?) → Standalone container
```

**Is this change code or config?**
```
Does graph logic / structure change?
 ├─ no  (prompt / model / tools) → new ASSISTANT VERSION  → canary → promote/rollback (no deploy)
 └─ yes (nodes / edges / tools code) → new DEPLOYMENT REVISION → rolling update (state survives in Postgres)
```

**How do I roll it out?**
```
Reversible in one step?  (config = yes; code = slower)
 → canary a small traffic slice → compare to incumbent on the same dashboards
   ├─ healthy  → shift fully
   └─ degraded → roll back (re-point version / redeploy prior revision)
```

**Should this fire an alert or just sit on a dashboard?**
```
Does it mean users are hurt NOW and someone must act?
 ├─ yes → ALERT (page): error spike, p99 blowout, traffic flatline, budget breach
 └─ no  → WATCH (dashboard): cost creep, feedback drift, model mix, per-tenant latency
```

**A run failed in prod — what now?**
```
Open the trace → reproduce → (time travel to rewind/edit/replay a fix)
 → add the reproducing run to the regression dataset → fix behind the CI gate → ship via version/revision
```

### How this generalises to complex multi-agent systems

The reason to trust the pattern on hard systems is that complexity lands *inside* the boxes, not between them:

- **One manifest, many graphs.** A supervisor + specialists still deploys from one `langgraph.json` exposing multiple graphs. Packaging is unchanged (02).
- **Subgraphs are still one deployment.** A graph with subgraphs (`docs/02-langgraph/09-subgraphs.md`) and HITL interrupts (`docs/02-langgraph/07-human-in-the-loop-interrupts.md`) is one Agent Server behind one Threads/Runs API. The contract is unchanged (02).
- **Config surface grows, mechanism doesn't.** Each sub-agent's prompt/model is more assistant config, versioned and canaried the same way (03, 05).
- **More spans, same traces.** A multi-agent run is a deeper trace tree. Dashboards, sampling, and alerts read it identically — you just group by agent/node too (04).
- **Failures are richer, capture is identical.** More places to fail means more automation rules feeding datasets, but the loop is the same (05).
- **Rollback still favours config.** Re-pointing one sub-agent's assistant version is still the fast, reversible path (05).

The one place complexity genuinely changes the *work* (not the pattern): **evaluation gets harder.** Multi-step, multi-agent runs need trajectory/step-level evaluators, not just final-answer scoring, and more failure modes to cover in the dataset (`docs/05-expert/05-multi-agent-system-design.md`, `docs/05-expert/08-evaluation-driven-development.md`). Everything else on the map is the same walk you did for `support-triage`.

## Why it matters

The value of a pattern over a recipe is that the recipe expires and the pattern does not. LangChain will rename products and change CLI flags again; when it does, this concern → feature map is how you re-map in an afternoon instead of relearning production from scratch. More importantly, the map is what lets you say *yes* to building something complex. A twelve-agent system is intimidating as a monolith and routine as "the same twenty-two concerns, each already wired to a feature I know." That is the whole point of carrying `support-triage` end to end: you were never learning one app, you were learning the loop that makes any agent operable.

## Pitfalls

- **Cherry-picking the map.** Skipping "durability" or "rollback" because the demo works is how a demo becomes an incident. The rows are load-bearing; a blank row is a risk you have chosen not to see.
- **Recipe thinking.** Memorising `langgraph deploy` instead of the pattern leaves you stranded when the command changes. Learn the concern; look up the current syntax.
- **Adding complexity before the loop exists.** Standing up a multi-agent system without tracing, a dataset, and a gate means you scaled the surface faster than your ability to see or fix it. Wire the loop on the simple version first.
- **Treating the checklist as one-time.** It is a *loop*. The go-live list gets you live; the concern map keeps you honest every iteration after.
- **Deploying code for what config could do.** The single most common waste: redeploying for changes that are assistant versions. Check the code-or-config tree every time.

## Exercises

1. Take an agent you have not yet productionised and fill in the concern → feature map for it. Every blank row is a task — order them and name the first.
2. Run the go-live checklist against a real deployment (or a staging one). Which boxes are red, and what is the smallest change that turns the reddest one green?
3. Walk the decision trees for one real upcoming change: is it code or config, how do you roll it out, and what is the rollback? Write the answer before you touch anything.
4. Take a genuinely complex agent design (multi-agent, subgraphs, HITL) and map it onto this pattern box by box. Identify the *one* box where the work actually gets harder (hint: evaluation) and describe how you would handle it.

## Further reading

- LangSmith Deployment overview: https://docs.langchain.com/langsmith/deployment
- Agent Server: https://docs.langchain.com/langsmith/agent-server
- LangGraph CLI: https://docs.langchain.com/langsmith/cli
- Evaluation concepts: https://docs.langchain.com/langsmith/evaluation-concepts
- This track: files `01`–`05` in `docs/06-production/`
- Sibling depth: `docs/05-expert/05-multi-agent-system-design.md`, `docs/05-expert/06-production-reliability.md`, `docs/05-expert/08-evaluation-driven-development.md`
