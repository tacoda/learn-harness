# 01 · The Path to Production

## Mental model

Everything before this track taught you to *build* an agent. This track teaches you to *operate* one. Those are different disciplines, and the second one never ends: a production agent is not a thing you ship once, it is a loop you run forever.

The whole track is one diagram. Learn it now and the rest is just filling in each box:

```
        ┌──────────────────────────────────────────────────────────┐
        │                                                            │
        ▼                                                            │
     build ──▶ trace ──▶ eval ──▶ deploy ──▶ monitor ──▶ feedback ──┘
   (a graph)  (see it)  (gate it) (serve it) (watch it) (learn from it)
      │          │         │         │          │           │
   create_    LangSmith  offline   Agent      LangSmith   real traces
   agent /    tracing    datasets  Server /   dashboards  → datasets
   StateGraph            + judges  Platform   + alerts    → next eval
```

Two things about this loop are the entire point of the track:

1. **It is a loop, not a line.** The arrow from `feedback` back to `build` is the most important arrow. Production traffic is the richest source of test cases you will ever have; a mature system converts real failures into datasets that gate the next change. Teams that treat deployment as the finish line ship once and then fly blind.
2. **It is the same loop at every scale.** A one-node `create_agent` and a twelve-agent supervisor system run the *identical* lifecycle. The boxes get bigger, the wiring does not change. That is why we insist on the pattern over the recipe: learn the loop on something trivial and you can operate something complex.

We carry one running example through the whole track: **`support-triage`**, a single-node `create_agent` that reads a customer message, calls a couple of tools (look up an order, search a help centre), and returns a reply or escalates. It is deliberately boring. The discipline around it is what makes it production-grade, and that discipline is what transfers.

## In depth

### The promotion pipeline: local → staging → prod

The lifecycle loop runs inside a second structure: code is *promoted* through environments, and it only moves forward when it clears a gate.

```
 local          staging                     production
 ┌─────┐  eval  ┌─────────┐  eval + canary  ┌──────────┐
 │ dev │──gate─▶│ staging │──────gate──────▶│   prod   │
 └─────┘        └─────────┘                 └──────────┘
 langgraph dev  deployed Agent Server       deployed Agent Server
 in-memory      Postgres-backed             Postgres-backed, real traffic
 you + Studio   synthetic / replayed load   real users, full monitoring
```

- **Local** is `langgraph dev` (file 02): an in-memory Agent Server on your laptop, driven from Studio, wired to LangSmith tracing from the first run. Fast, disposable, no durability guarantees.
- **Staging** is a *real* deployment — same `langgraph.json`, same Postgres-backed server as prod — but it takes no real user traffic. It is where the offline eval suite runs against a production-like server and where you rehearse rollout.
- **Production** takes real traffic, emits the traces that feed monitoring and the feedback loop, and is the thing you must be able to roll back in seconds.

The gates between stages are not optional review meetings; they are **automated eval runs** (files 05 and `docs/03-langsmith/08-testing-in-ci-cd.md`). A change that regresses the dataset does not get promoted. This is what "evaluation-driven development" (`docs/05-expert/08-evaluation-driven-development.md`) looks like once it has a deployment attached.

### What "production-ready" means for an agent

An agent is production-ready when you can answer *yes* to all of these — and note that only the first is about the agent's code:

- **Correct enough, measured.** There is a dataset and an evaluator suite, and the current version's score on it is known, not guessed.
- **Durable.** State is checkpointed to Postgres, not RAM, so a crash resumes instead of losing work (`docs/02-langgraph/05-persistence-checkpointers.md`, `docs/05-expert/06-production-reliability.md`).
- **Observable.** Every run emits a trace; latency, cost, error rate, and feedback are on a dashboard (file 04).
- **Alertable.** Something pages a human when a metric crosses a threshold, rather than a user discovering the outage for you.
- **Reversible.** You can roll back to the previous known-good version in one step — for an agent, usually a previous *assistant version*, not a redeploy (files 03, 05).
- **Improvable.** There is a defined path from a bad production run to a new test case to a fixed version. The loop is closed.

"The demo works" satisfies none of these. That is the gap this track closes.

### How the rest of the track fills in the diagram

| Box in the loop | File | The reusable concern |
|---|---|---|
| build → package | 02 · Packaging & Assistants | turn a graph into a deployable unit with a stable API |
| deploy | 03 · Deploying | get that unit running durably, in the right environment |
| monitor | 04 · Monitoring | see production health continuously and get paged |
| feedback → eval → build | 05 · Maintenance & Iteration | close the loop; ship changes without breaking prod |
| (all of it) | 06 · The Production Pattern Checklist | the distilled, app-agnostic playbook |

## Why it matters

The reason to internalise the *pattern* rather than memorise a deploy command is that the command will change and the pattern will not. LangChain has already renamed and reorganised this surface more than once (the platform now lives under "LangSmith Deployment"; the runtime is the "Agent Server"). What has stayed constant across every rename is the shape: package a graph, serve it with durable state behind a stable API, observe it, evaluate it, and feed production reality back into the next version.

That shape is also what lets you graduate from `support-triage` to a real system. A multi-agent research assistant with subgraphs and human-in-the-loop interrupts is dramatically more code — but it packages into the same `langgraph.json`, deploys to the same Agent Server, emits the same traces, and is gated by the same eval loop. You do not learn a new operational model when your agent gets complex. You learn this one once.

## Pitfalls

- **Treating deploy as the finish line.** The `feedback → build` arrow is where the value compounds. If you ship and stop, you have a static artifact degrading against a drifting world.
- **No environment separation.** Testing in prod because "staging is a hassle" means your first real eval is your users. Stand up staging with the same manifest before you have traffic to lose.
- **Gates that are advisory.** A regression check nobody blocks a merge on is documentation, not a gate. Wire eval into CI so a regression *stops* promotion (file 05).
- **Confusing a version bump with a code change.** Much of production iteration for an agent is configuration (prompt, model, tools) expressed as a new *assistant version* — no redeploy, instant rollback. Reaching for a code deploy for every tweak is slow and risky (files 02, 03, 05).
- **Building the pattern for the complex case first.** Learn the loop on `support-triage`. Scaling it to a multi-agent system is additive, not a rewrite — but only if you actually learned it on the simple thing.

## Exercises

1. Draw the lifecycle loop from memory and label each box with the specific LangGraph or LangSmith feature that implements it. Where does *your* current project break the loop?
2. For an agent you have built, write down concrete pass/fail answers to the six "production-ready" questions. Which are red today, and which single one would you fix first?
3. Describe your local → staging → prod pipeline as it exists now. If any stage is missing, name what would have to be true to add it.
4. Take a genuinely complex agent design (multi-agent, HITL, subgraphs) and argue in a paragraph why it runs the *same* lifecycle as `support-triage`. Identify the one place the complexity actually changes the operational work.

## Further reading

- LangSmith Deployment overview: https://docs.langchain.com/langsmith/deployment
- Agent Server (the runtime): https://docs.langchain.com/langsmith/agent-server
- Evaluation concepts (offline vs online): https://docs.langchain.com/langsmith/evaluation-concepts
- Sibling tracks: `docs/05-expert/08-evaluation-driven-development.md`, `docs/05-expert/06-production-reliability.md`, `docs/03-langsmith/08-testing-in-ci-cd.md`
