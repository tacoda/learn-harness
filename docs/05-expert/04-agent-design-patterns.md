# 04 · Agent Design Patterns

## Mental model

There is a spectrum, and every design decision is a point on it. At one end: **workflows** — "predetermined code paths," where you (the engineer) decide the control flow and the LLM fills in the text. At the other: **agents** — the model decides its own path, calling tools in a loop until done. LangChain's guidance is to see these not as rival philosophies but as a dial you turn per sub-problem: use the *least* agency that solves the task reliably.

The patterns below are the named points on that dial. The novice mistake is to reach for the most agentic option ("just give the model all the tools and let it figure it out") because it's the least code. The expert move is the opposite: **start with the most constrained pattern that works, and add agency only where the task genuinely needs the model to make control-flow decisions.** More agency means more ways to fail and more tokens spent; you buy it deliberately.

Each pattern maps to a concrete LangGraph or `create_agent` implementation. Knowing the mapping — and the "when" — is the payoff.

## In depth

### Prompt chaining (workflow)

Decompose a task into a fixed sequence of model calls, each operating on the previous output. No branching on model decisions; the chain is hard-coded.

*Implementation:* a linear `StateGraph` — nodes wired `START → generate → improve → polish → END`, each a model call reading and writing state. (Or `prompt | model | parser` Runnables composed with `|` for the simplest cases; or the functional API with `@task`/`@entrypoint`.)

*When:* the task has clean, stable subtasks with a known order — draft then critique then polish; extract then transform then format. The most reliable pattern because there's no model-driven control flow to go wrong.

### Routing / classifier (workflow)

A first model call classifies the input, and a conditional edge dispatches to the specialized handler for that class.

*Implementation:*

```python
def classify(state) -> dict:
    label = router_model.invoke(state["messages"]).content
    return {"route": label}

def pick(state) -> str:
    return state["route"]   # "billing" | "technical" | "general"

builder.add_conditional_edges("classify", pick,
    {"billing": "billing_agent", "technical": "tech_agent", "general": "general_agent"})
```

*When:* inputs fall into distinct categories that each want a different prompt, toolset, or even model. Routing lets you use a *cheap* classifier and a *strong* specialist — a direct cost lever (`07-cost-and-latency-optimization.md`). It also keeps each handler's context narrow (`03-context-engineering.md`).

### Parallelization (workflow)

Run independent subtasks concurrently and aggregate. Two flavors: static (fixed set of parallel branches — e.g. run three graders and vote) and dynamic (unknown count at runtime).

*Implementation:* static = multiple edges out of one node into a join node with an `operator.add` reducer on the shared channel. Dynamic = the `Send` API (see orchestrator-worker).

*When:* subtasks don't depend on each other. Parallelization cuts wall-clock latency and enables ensemble/voting patterns. The reducer choice on the aggregation channel *is* the design (`02-graph-engineering.md`).

### Orchestrator-worker (agentic + workflow hybrid)

An orchestrator model decides *at runtime* how to break the task into pieces, spawns a worker per piece, and synthesizes the results. Unlike static parallelization, the number and shape of workers is model-decided.

*Implementation:* the `Send` API, LangGraph's built-in support for exactly this:

```python
from langgraph.types import Send

def assign_workers(state):
    # orchestrator produced state["sections"]; fan out one worker each
    return [Send("write_section", {"section": s}) for s in state["sections"]]
```

Each worker has its own state slice; all write to a shared `Annotated[list, operator.add]` channel the synthesizer reads.

*When:* the task decomposes but you can't know the decomposition in advance — writing a report whose sections depend on the topic, fanning out research subtopics. This is the backbone of many "deep" agents.

### Evaluator-optimizer (agentic loop)

One model generates, a second *evaluates* against criteria, and if it fails the generator retries with the feedback — a loop that refines until the evaluator passes or a bound trips.

*Implementation:* a two-node cycle with a conditional edge:

```python
def evaluate(state) -> str:
    verdict = grader.invoke(...)   # "pass" | "fail"
    return verdict

builder.add_conditional_edges("evaluate", route,
    {"fail": "generate", "pass": END})
```

Bound the loop (a counter in state or `recursion_limit`) so a stubborn evaluator can't spin forever.

*When:* quality matters and you have measurable criteria — code that must compile, output that must satisfy a rubric, translations refined against a quality check. The evaluator is often a cheaper model or a deterministic check.

### Reflection (agentic)

A special case of evaluator-optimizer where the *same* model critiques its own output and revises. Cheaper to build (one model), weaker than an independent evaluator (a model is a poor judge of its own work). Use when an external criterion is hard to specify but self-critique still lifts quality.

### ReAct — the tool-calling agent (agentic)

The default agent: reason, act (call a tool), observe, repeat. This *is* `create_agent`.

```python
from langchain.agents import create_agent
agent = create_agent(model="anthropic:claude-sonnet-4-6", tools=[search, calc])
```

*When:* the task needs the model to decide *which* actions to take and *in what order*, based on intermediate results — open-ended research, interactive problem-solving, anything where you can't pre-draw the control flow. The most flexible and the most failure-prone; bound it (Loop 1, `01-the-agent-loop-and-loop-engineering.md`) and engineer its context hard.

### Plan-and-execute (agentic)

Separate *planning* from *doing*: a planner produces an explicit multi-step plan up front, then an executor works the steps (often each step is itself a ReAct call), optionally re-planning when reality diverges.

*Implementation:* a planner node writes a `plan` list to state; an executor node (or subgraph) consumes steps; a conditional edge loops back to re-plan if needed. deepagents formalizes the plan-to-a-todo-list version (`docs/04-deepagents/02-planning-and-todos.md`).

*When:* long-horizon tasks where a pure ReAct loop loses the thread — the explicit plan is durable context that survives many tool rounds. Trade-off: an up-front plan can be wrong, so allow re-planning.

### Choosing the pattern

| Task shape | Pattern |
|---|---|
| Fixed sequence of steps | Prompt chaining |
| Distinct input categories | Routing |
| Independent subtasks, known set | Parallelization |
| Model-decided decomposition | Orchestrator-worker |
| Measurable quality bar, needs refinement | Evaluator-optimizer |
| Open-ended, model picks actions | ReAct (`create_agent`) |
| Long-horizon, needs a durable plan | Plan-and-execute |

Real systems compose these: a router (cheap) dispatches to a plan-and-execute agent whose executor steps are ReAct loops, each bounded and evaluated. Patterns are Lego bricks, not exclusive choices.

## Why it matters

Most "the agent is unreliable" problems are really "we used too much agency for this sub-task." A step that could be a hard-coded chain was left to the model's discretion, so it sometimes chooses wrong. Picking the *least agentic pattern that works* is the single most effective reliability lever after context engineering — and it's cheaper and faster too. The patterns give you a vocabulary for making that choice deliberately instead of defaulting to "give it all the tools."

## Pitfalls

- **Defaulting to ReAct for everything.** If you can draw the control flow, encode it as a workflow. Reserve the open-ended loop for genuinely open-ended tasks.
- **Unbounded evaluator-optimizer / reflection loops.** Always cap the refine cycle; a model that never satisfies its own critic will spin.
- **Reflection where an independent evaluator was needed.** Self-critique is weak; if you have an objective criterion, use a separate evaluator (or a deterministic check).
- **Static parallelization with an overwrite reducer.** Concurrent workers writing the same channel clobber each other. Use `operator.add` on the aggregation channel.
- **Orchestrator-worker without bounding worker count.** A model that decides to spawn 200 workers will surprise your budget. Cap the fan-out.

## Exercises

1. For a task you're building, place it on the workflow↔agent spectrum and name the single pattern that uses the least agency while still solving it. Justify.
2. Implement a router that sends "simple" queries to a cheap direct model call and "complex" ones to a full ReAct agent. Measure the cost difference over a realistic input mix.
3. Build an evaluator-optimizer loop where the evaluator is a deterministic check (e.g. "the generated JSON parses"). Add a loop bound and prove it terminates on adversarial input.
4. Convert a monolithic ReAct agent that "does research and writes a report" into an orchestrator-worker graph using `Send`. Note what became more testable.

## Further reading

- Workflows and agents (all patterns, with code): https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Anthropic — Building effective agents (the pattern taxonomy this builds on): https://www.anthropic.com/engineering/building-effective-agents
- How to think about agent frameworks (workflow↔agent spectrum): https://blog.langchain.com/how-to-think-about-agent-frameworks/
- LangGraph track: `docs/02-langgraph/03-nodes-edges-control-flow.md`, `04-prebuilt-react-agent.md`, `10-multi-agent-architectures.md`
