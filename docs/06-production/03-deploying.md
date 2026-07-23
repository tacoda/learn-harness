# 03 · Deploying

## Mental model

Deploying an agent is the step where the deployable unit from file 02 starts running durably, takes traffic, and survives restarts. The mental model has two axes, and every deployment decision lives on one of them:

```
   WHERE it runs (deployment option)          HOW it moves (promotion + rollout)

   Cloud ──── Hybrid ──── Self-hosted          local ──▶ staging ──▶ prod
     │          │             │                          (eval gate)
   most      your VPC,     your infra,         within a stage:
   managed   managed CP    everything          new assistant version
                                               canary → promote / roll back
     └──── Standalone (runtime only) ────┘
```

The first axis (**where**) is a one-time architectural choice driven by data residency and how much infrastructure you want to own. The second axis (**how**) is the thing you do constantly. The reusable pattern is that the graph and `langgraph.json` are *identical across every option and every stage* — deployment is configuration and packaging, never a rewrite. Choosing Cloud vs self-hosted changes who runs Postgres; it does not change your agent.

## In depth

### The deployment options and their tradeoffs

LangSmith Deployment runs the **Agent Server** in four configurations. The split is about where the *control plane* (the management layer) and the *data plane* (your running agents and their databases) live.

| Option | Control plane | Data plane (agents + DBs) | Choose when |
|---|---|---|---|
| **Cloud (SaaS)** | LangChain | LangChain (AWS/GCP) | You want it fully managed. Deploy from GitHub, automated CI/CD, autoscaling, Studio — nothing to operate. Default choice. |
| **Hybrid** | LangChain | **Your** VPC | Data/compute must stay in your infra for compliance, but you want the managed control plane. Traces go to LangSmith Cloud or self-hosted. |
| **Self-hosted** | **You** | **You** | Full data residency or air-gapped. Enterprise add-on; you run the control plane *and* the Agent Servers alongside self-hosted LangSmith. |
| **Standalone container** | none | **You** | You just want the agent runtime. Run Agent Server containers with Docker/Compose/Kubernetes, bring your own Postgres + Redis + license. No control plane; optional tracing to Cloud. |

The tradeoff is a straight line from *least operational burden, least control over data* (Cloud) to *most burden, most control* (Self-hosted / Standalone). The recommendation for almost everyone starting out: **Cloud**, and move down the table only when a concrete compliance or residency requirement forces you. Do not pay the self-hosting tax speculatively.

The generalisation: this table is the same whether you deploy `support-triage` or a multi-agent system. The agent's complexity is orthogonal to where it runs.

### The deploy workflow and CLI

The CLI (`langgraph-cli`) is the same tool from file 02; deployment adds three commands beyond `dev`:

```bash
# Build a Docker image of the Agent Server around your graph
langgraph build -t support-triage:1.4.0        # -t/--tag is required

# Run that image locally with a real (Compose) stack — Postgres + Redis
langgraph up --port 8123                        # needs a LangSmith API key

# Build + push + create/update a Cloud deployment in one step  (beta)
langgraph deploy -t support-triage:1.4.0
```

- **`langgraph build -t <tag>`** produces the deployable image. Add `--platform linux/amd64,linux/arm64` for multi-arch.
- **`langgraph up`** runs that image locally against a real Compose stack (Postgres for state, Redis for the task queue) — this is your "production-like on a laptop" check, closer to prod than `langgraph dev`. Point it at an external DB with `--postgres-uri`.
- **`langgraph deploy`** (beta, Cloud only) builds, pushes to the managed registry, and creates or updates the deployment. If Docker is not installed it triggers a remote build.
- **`langgraph dockerfile <path>`** emits a plain Dockerfile if you need to build in your own pipeline (the Standalone path).

For Cloud, the common real-world workflow is **GitHub-based**: connect the repo, and the platform builds and deploys on push automatically. `langgraph deploy` is the imperative version of the same thing. Either way the input is the `langgraph.json` from file 02 — "any app that exports a graph from a `langgraph.json` deploys the same way, regardless of which framework authored the agent."

### Postgres persistence, and why it is non-negotiable

The Agent Server always persists its core resources — **assistants, threads, runs, cron jobs** — in **Postgres**. On top of that:

- **Checkpoints** (short-term, per-thread state) are written to Postgres by default. Durability mode controls frequency: `async` (default) writes after each super-step so a crash resumes from the last step; `exit` stores only the final state (cheaper, less granular recovery). Backend is swappable to MongoDB or custom via the manifest's `checkpointer` key.
- **Store** (long-term, cross-thread memory) is Postgres by default.
- **Redis** carries the task queue: signalling, cancellation, and streaming pub/sub between API servers and queue workers. It holds only ephemeral data — no run or user data lives in Redis; that is always Postgres.

This is the production teeth behind `docs/05-expert/06-production-reliability.md` and `docs/02-langgraph/05-persistence-checkpointers.md`: **`InMemorySaver` in production is total, silent data loss on restart.** In a managed deployment you get Postgres for free; in Standalone you must bring your own. The rule that scales: durable state is a property of the *deployment*, not the graph — which is why the graph in file 02 carries no checkpointer.

### Scaling and concurrency

The Agent Server separates the **API server** (accepts requests, streams responses) from **queue workers** (execute graph runs). It supports three runtime shapes:

- **Single host** — API and queue in one process. Fine for low volume and local testing.
- **Split API and queue** — separate processes for serving and execution; scale them independently.
- **Distributed** — separate orchestration and execution processes for high-concurrency, large-scale deployments.

Because workers are **stateless and share the Postgres checkpoint store**, any worker can resume any thread — this is what makes horizontal scaling and crash recovery work (a run interrupted on worker A resumes on worker B from its last checkpoint). On Cloud, scaling is automatic. Self-hosted/Standalone, you scale worker replicas yourself. `--n-jobs-per-worker` tunes per-worker concurrency. The concurrency model does not change with agent complexity; a slow multi-agent run just occupies a worker longer.

### Environments: staging vs prod

Stand up **two deployments from the same `langgraph.json`** — `support-triage-staging` and `support-triage-prod` — differing only in environment variables and which traffic they receive:

- **Staging** — Postgres-backed, production-like, but fed synthetic or replayed traffic. It is where the offline eval suite runs against a real server (file 05) and where you rehearse rollout.
- **Prod** — real traffic, full monitoring (file 04), the thing you must be able to roll back.

Keep secrets per-environment (staging keys ≠ prod keys) and point each at its own database. The generalisable rule: **environments are copies of the same manifest with different config and traffic**, so adding a third (`canary`, `eu-prod`) is cheap.

### Zero-downtime and assistant versioning

Two different mechanisms, for two different kinds of change:

- **Code changes** (graph logic) require a new deployment revision. The platform does a rolling update: new revision comes up, health-checks pass, traffic shifts, old revision drains. Because state is in Postgres (not in the process), in-flight threads survive the swap — this is why graceful, stateless workers matter.
- **Config changes** (prompt, model, tools) do **not** need a deploy at all. Create a **new assistant version**, shift traffic to it, and if it misbehaves point the assistant back at the prior version — rollback in one API call, no rebuild. This is the fast, safe path for most iteration and the foundation of the canary/staged rollout in file 05.

```python
# a code deploy ships a new graph revision; a config change is just a new version:
v2 = await client.assistants.update(
    assistant_id,
    context={"system_prompt": "Escalate billing disputes immediately."},
)   # creates a new version; roll back by re-pointing to the previous one
```

The pattern to carry forward: **prefer a version bump over a redeploy.** Versioned assistants turn most production changes into reversible, zero-downtime, no-build operations — and that property is worth an order of magnitude more on a complex system than on `support-triage`.

## Why it matters

Deployment is where the reliability engineering of `docs/05-expert/06-production-reliability.md` becomes real infrastructure rather than good intentions. The Agent Server hands you durable Postgres-backed state, stateless horizontally-scalable workers, rolling zero-downtime updates, and versioned config rollback — the exact machinery that is tedious and error-prone to rebuild and easy to get subtly wrong around persistence and resumption. The strategic payoff is that all of it is driven by the same `langgraph.json` across Cloud, hybrid, self-hosted, and standalone: you make the *where* decision once, based on data residency, and then never revisit your agent code to change deployment target. That decoupling — agent code on one axis, infrastructure on another — is what lets a simple agent and a complex one share an operational playbook.

## Pitfalls

- **`InMemorySaver` / no Postgres in production.** Silent total durability loss on restart. Managed deployments give you Postgres; Standalone means you must provision it. Never ship in-memory state to prod.
- **Self-hosting speculatively.** Start on Cloud. Move to hybrid/self-hosted only when a concrete compliance or residency requirement forces it — the operational tax is real.
- **Redeploying for a prompt tweak.** A config change is a new assistant version: zero downtime, instant rollback, no build. Reaching for a code deploy makes every change slow and risky.
- **No staging.** Running the offline eval gate against prod, or first meeting a regression in prod, means your users are the test suite. Stand up staging from the same manifest.
- **Non-idempotent tools under a rolling update or worker retry.** At-least-once execution means a step can replay across a deploy or crash. Charging a card twice is a deployment bug, not just a code bug — make side-effecting tools idempotent (`docs/05-expert/06-production-reliability.md`).
- **Sharing databases across environments.** Staging writing to the prod store corrupts real state and pollutes real traces. One database per environment.

## Exercises

1. For your own app, pick a deployment option from the table and justify it in two sentences, naming the specific data-residency or operational driver. What would have to change to move you down the table?
2. Run `langgraph build -t <app>:dev` then `langgraph up`, and confirm state now survives a server restart (create a thread, restart, read its history). Contrast with `langgraph dev`.
3. Stand up a staging and a prod deployment from one `langgraph.json` with different env. Describe exactly what differs between them and what stays identical.
4. Make a config-only change to `support-triage` as a new assistant version, shift traffic, then roll it back by re-pointing to the prior version. Time both operations. Now describe why doing the same as a code deploy would be slower and riskier.

## Further reading

- LangSmith Deployment (options overview): https://docs.langchain.com/langsmith/deployments
- Cloud (SaaS): https://docs.langchain.com/langsmith/cloud
- Self-hosted: https://docs.langchain.com/langsmith/self-hosted
- Deploy to cloud (quickstart): https://docs.langchain.com/langsmith/deployment-quickstart
- LangGraph CLI (`build`, `up`, `deploy`): https://docs.langchain.com/langsmith/cli
- Agent Server (persistence, runtime architecture): https://docs.langchain.com/langsmith/agent-server
- Sibling: `docs/02-langgraph/13-deployment-langgraph-platform.md`, `docs/05-expert/06-production-reliability.md`, `docs/05-expert/07-cost-and-latency-optimization.md`
