# 01 · The Agent Loop & Loop Engineering

## Mental model

An agent is not a model, and it is not a graph. It is a **loop**: the model proposes an action, something executes that action, the result is observed, and the model is called again with the result in its context. LangChain states this in one sentence — "an agent is a model calling tools in a loop until a given task is complete" — and pairs it with a formula worth memorizing:

```
Agent = Model + Harness
```

The *model* decides. The *harness* is everything around the decision: the prompt, the tools, the middleware, the state, the persistence, the guardrails. The harness's entire job is to **get the model the right context at the right time**. Every expert-level concern in this track — context engineering, graph design, reliability, cost — is ultimately a statement about the harness that wraps the loop.

Once you see the agent as a loop, the natural next question is: *how many loops are there, and who bounds each one?* A production agentic system is not one loop but **four nested loops**, each running on a different timescale and owned by a different part of the stack:

```
┌─ Loop 4: EVALUATION  (days)      build → trace → eval → improve
│  ┌─ Loop 3: HUMAN-IN-THE-LOOP  (minutes)   pause → review → resume
│  │  ┌─ Loop 2: DURABILITY/RECOVERY  (seconds)   fail → checkpoint → retry/replay
│  │  │  ┌─ Loop 1: THE AGENT LOOP  (100s of ms)   model → tools → observe → repeat
│  │  │  └─
│  │  └─
│  └─
└─
```

Loop-engineering discipline is knowing which loop a given problem belongs to, and bounding each loop deliberately rather than letting it run away. A runaway inner loop burns tokens; an unbounded recovery loop replays a side effect forever; a human loop with no timeout blocks a thread indefinitely; an evaluation loop that never closes means you ship on vibes. The "four loops" is a design lens, not an official LangChain framework — but each loop maps cleanly onto concrete features across LangChain, LangGraph, and LangSmith, and that mapping is the point.

## In depth

### Loop 1 — the inner agent/tool loop

This is the loop the word "agent" usually refers to. In LangChain 1.x it is `create_agent`, which compiles to a two-node LangGraph cycle: a **model node** and a **tools node** connected by a conditional edge.

```python
from langchain.agents import create_agent

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[search, fetch_page],
)
result = agent.invoke({"messages": [{"role": "user", "content": "Research X"}]})
```

The loop's logic: call the model → if the model emitted tool calls, run them and append the results as `ToolMessage`s → call the model again → repeat until the model responds with no tool calls (task complete). This is the ReAct pattern, but you no longer hand-write it — see `docs/01-langchain/09-agents-create-agent.md`.

**Failure modes.** The inner loop fails by *not terminating* (the model keeps calling tools, never converging), by *thrashing* (repeating the same failing tool call), or by *drowning* (each turn appends more tool output until the context window overflows). All three are loop-shape problems, not model problems.

**How to bound it.** The primary bound is LangGraph's `recursion_limit` — the maximum number of super-steps before the runtime raises `GraphRecursionError`:

```python
agent.invoke(inputs, {"recursion_limit": 25})
```

That is a hard ceiling. A softer, steerable bound is the managed `RemainingSteps` value, which lets a node *see* how close it is to the limit and wind down gracefully instead of crashing:

```python
from langgraph.managed import RemainingSteps

class State(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: RemainingSteps  # auto-populated by the runtime

def route(state) -> str:
    if state["remaining_steps"] <= 2:
        return "wrap_up"      # give a best-effort answer instead of another tool round
    return "continue"
```

The most surgical bounds are **middleware guards** wrapped around the model or tool calls — a `before_model` hook that injects "you have used N of M tool calls, converge now," or a `wrap_tool_call` hook that short-circuits a tool the agent has already called with identical arguments. Middleware is the v1 idiom for steering the loop without forking it (`docs/01-langchain/10-middleware.md`).

### Loop 2 — the retry / durability / recovery loop

The inner loop assumes each step succeeds. Reality: tools time out, providers rate-limit, processes crash mid-run. Loop 2 is the loop that makes progress *survive* failure. It maps to **checkpointers**: LangGraph persists state at every super-step boundary, so a crashed run resumes from the last completed step rather than the beginning.

```python
from langgraph.checkpoint.postgres import PostgresSaver

agent = create_agent(model=..., tools=..., checkpointer=PostgresSaver(...))
agent.invoke(inputs, {"configurable": {"thread_id": "abc"}})
# process dies here → re-invoke with the same thread_id → resumes mid-flight
```

**Failure modes.** Replaying a step that had a *non-idempotent side effect* (charging a card, sending an email) re-executes it. An unbounded retry loop hammers a down provider. `InMemorySaver` "works" in dev and silently loses everything on restart in prod.

**How to bound it.** Use `.with_retry(...)` on the Runnable for transient errors with backoff, and `.with_fallbacks(...)` for degradation. Design side-effecting tools to be idempotent (dedupe keys). Never ship `InMemorySaver`; use `SqliteSaver` for dev, `PostgresSaver` for prod. This loop is covered in depth in `docs/02-langgraph/11-durable-execution-and-time-travel.md` and expanded in this track's `06-production-reliability.md`.

### Loop 3 — the human-in-the-loop

Some actions are too consequential to let the model take unsupervised. Loop 3 pauses the machine, hands control to a person, and resumes with their decision folded into state. It maps to LangGraph **interrupts** plus the `HumanInTheLoopMiddleware`:

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

agent = create_agent(
    model=..., tools=[write_file, execute_sql],
    middleware=[HumanInTheLoopMiddleware(interrupt_on={
        "execute_sql": {"allowed_decisions": ["approve", "edit", "reject"]},
    })],
    checkpointer=PostgresSaver(...),   # HITL requires persistence
)
```

The four decision types — `approve`, `edit`, `reject`, `respond` — are the full vocabulary of human oversight. The interrupt halts the graph, checkpoints it, and returns control to your application; a person reviews; `Command(resume=...)` continues from exactly where it paused. This is *why* Loop 3 is built on Loop 2: HITL is impossible without durable state.

**Failure modes.** No timeout on the human step blocks a thread forever. Interrupting on *every* tool call trains reviewers to rubber-stamp. Forgetting the checkpointer makes HITL silently impossible.

**How to bound it.** Gate interrupts behind a `when` predicate so only genuinely risky calls surface (write queries, out-of-workspace writes). Detail lives in `docs/02-langgraph/07-human-in-the-loop-interrupts.md` and this track's `11-security-and-guardrails.md`.

### Loop 4 — the evaluation / improvement loop

The outermost, slowest loop is how the *system itself* gets better: **build → trace → eval → improve**. You ship a version, it emits traces to LangSmith, you harvest failures into a dataset, you run evaluators against that dataset, you fix, and you gate the fix with the same evals. This is the loop that turns "seems fine" into evidence.

It maps to LangSmith tracing (`docs/03-langsmith/01-tracing-and-observability.md`), datasets built from production runs (`docs/03-langsmith/02-datasets.md`), and `client.evaluate(...)` experiments (`docs/03-langsmith/03-evaluation-and-experiments.md`).

**Failure modes.** The loop never closes — you trace but never build datasets, or you eval once and never gate CI on it. Evals drift from production because the dataset is synthetic rather than harvested from real traces.

**How to bound it.** Treat evals as tests with a regression gate in CI (this track's `08-evaluation-driven-development.md`). The bound here is not a numeric limit but a *cadence*: every incident becomes a dataset example, every release runs the suite.

### The loops interlock

The loops are nested, and each outer loop depends on the machinery of the inner ones. Loop 3 (human) is built on Loop 2 (durability). Loop 4 (eval) observes Loop 1 (agent) through tracing. When you debug an agent, first ask *which loop is misbehaving* — a non-terminating inner loop, a replay re-firing a side effect, a stuck human gate, or a stale eval set — because the fix lives in a different layer for each.

## Why it matters

Beginners treat the agent as a black box: prompt in, answer out. When it misbehaves they tune the prompt. Experts see four loops and diagnose which one is unbounded. That reframing is what makes the difference between an agent that demos and an agent that runs a business-critical workload. Harrison Chase's own framing of "what is hard about building agents" lands here: the hard part is reliability, and reliability is loop-engineering plus context-engineering, not model choice.

## Pitfalls

- **Conflating the loops.** "My agent is slow" might be Loop 1 (too many tool rounds), Loop 2 (retry storms), or Loop 3 (waiting on a human). The fix differs entirely.
- **No hard bound on Loop 1.** Without a `recursion_limit` a confused model can loop until it exhausts the context window or your budget. Always set one.
- **HITL without a checkpointer.** The interrupt has nowhere to save state; the pattern silently cannot work.
- **Skipping Loop 4.** An agent with no evaluation loop cannot improve — you are flying blind and every change is a gamble.
- **Replaying non-idempotent side effects.** Loop 2's recovery replays steps; if a tool isn't idempotent, recovery causes double-charges. Design for it.

## Exercises

1. Take a `create_agent` you have built. For each of the four loops, name the concrete feature (or absence of one) that implements it in your system today.
2. Add both a `recursion_limit` and a `RemainingSteps`-based graceful wind-down to an agent, then craft an input that would otherwise loop forever and confirm both bounds fire.
3. Write a `wrap_tool_call` middleware that detects and short-circuits a tool call identical to one already made this run. Which loop are you bounding?
4. Diagram your own system's four loops on the nesting diagram above and mark, for each, the failure mode you are least protected against.

## Further reading

- Agents (the agent loop, Model + Harness): https://docs.langchain.com/oss/python/langchain/agents
- How to think about agent frameworks (Harrison Chase): https://blog.langchain.com/how-to-think-about-agent-frameworks/
- How to build an agent: https://blog.langchain.com/how-to-build-an-agent/
- Durable execution / persistence: https://docs.langchain.com/oss/python/langgraph/durable-execution
- Human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- Evaluation concepts: https://docs.langchain.com/langsmith/evaluation-concepts
