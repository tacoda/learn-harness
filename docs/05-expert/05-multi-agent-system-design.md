# 05 · Multi-Agent System Design

## Mental model

The headline advice comes first because it's the advice most often ignored: **don't reach for multi-agent too early.** A single agent with well-chosen tools, good context engineering, and the right design pattern (`04-agent-design-patterns.md`) handles the large majority of tasks — with less code, less latency, and a fraction of the tokens. Anthropic measured their multi-agent researcher using up to **15× the tokens** of a single chat interaction. Multi-agent is a real tool with a real bill; you pay it when the task genuinely requires it, not because the architecture looks impressive.

When *is* it warranted? The honest answer from LangChain's context-engineering framing: multi-agent is primarily a **context isolation** technique. You split into multiple agents when a single context window can't hold — or shouldn't hold — everything the task needs, and the subtasks are separable enough that each agent can work in its own window with its own tools and instructions. If your subtasks constantly need to see each other's full context, multi-agent's communication overhead will eat the benefit and then some.

So the decision is: **isolation benefit vs. communication cost.** High isolation, low coordination → multi-agent wins. High coordination, shared context → keep it single-agent (perhaps as an orchestrator-worker workflow, which gives you parallelism without independent agents).

## In depth

### Single-agent-with-tools vs. multi-agent

Before splitting, ask whether you actually need *agents* or just *structure*. Orchestrator-worker (`04-agent-design-patterns.md`) gives you parallel, decomposed work inside a *single* state and graph — the workers are nodes, not autonomous agents with their own loops and memory. That's often what people reach for multi-agent to get, at a fraction of the complexity. Escalate to true multi-agent only when the sub-workers need their own tool sets, their own context windows, their own conversational memory, or their own model.

### The four topologies

**Supervisor.** A central agent routes work to specialist agents and integrates their results; specialists don't talk to each other, only back to the supervisor. This is the most common and most controllable topology — the supervisor is a single point to reason about, log, and gate. LangChain maintains `langgraph-supervisor` for this shape. Use when you have a clear coordinator role and specialists with disjoint expertise (a "research" agent, a "code" agent, a "math" agent).

**Swarm.** Agents hand control directly to one another based on who's best suited for the current step; there's no central router — control lives wherever the active agent passes it. LangChain maintains `langgraph-swarm`. Use when the "right next agent" is best judged locally by the current agent, and a central supervisor would be a bottleneck.

**Network.** Any agent can call any other — a fully connected graph. Maximally flexible, maximally hard to reason about and bound. Rarely the right first choice; the flexibility usually isn't worth the loss of legibility.

**Hierarchical.** Supervisors of supervisors — teams of agents, each team led by a supervisor, coordinated by a top-level supervisor. The scaling answer when a flat supervisor would have too many specialists to route among. Use only when a single supervisor's fan-out genuinely becomes unwieldy.

Default to **supervisor**. Escalate to hierarchical when the specialist count grows; reach for swarm when local handoff decisions beat central routing; treat network as a last resort.

### Handoffs

The mechanism that moves control between agents is a **handoff**, implemented with `Command`:

```python
from langgraph.types import Command

def transfer_to_researcher(state) -> Command:
    return Command(
        goto="researcher",           # jump to another node/agent
        update={"messages": [...]},  # what to hand over
        graph=Command.PARENT,        # navigate up to the parent graph if needed
    )
```

`Command(goto=...)` is the primitive: it says "go here next," optionally updating state as it transfers. The design question every handoff forces: **what context travels with the handoff?** Pass too little and the receiving agent is confused; pass the entire history and you've defeated the isolation that motivated multi-agent in the first place. Handoff payload design is context engineering (`03-context-engineering.md`) applied to agent boundaries.

### Shared vs. isolated state and memory

This is *the* architectural decision in a multi-agent system.

- **Isolated state** (each agent its own subgraph, own message history, own memory) maximizes the context benefit — each window stays narrow and task-focused. The cost is coordination: agents can't see each other's work except through explicit handoff payloads. This is the configuration that delivers the isolation win.
- **Shared state** (agents read/write common channels) makes coordination trivial but reintroduces the crowded-context problem you were trying to escape — every agent sees everyone's mess.

The productive middle: isolated working state per agent, plus a *small* shared channel for coordination artifacts (the plan, the final results being assembled). Model this with subgraphs and carefully chosen shared keys (`02-graph-engineering.md`). Memory follows the same logic: per-agent short-term memory (thread-scoped), with a shared Store for cross-agent facts only when genuinely shared.

### Communication overhead

Every agent-to-agent message is tokens, latency, and a place for context to be lost or garbled. Multi-agent systems fail not because the agents are individually bad but because the *seams* between them leak: a handoff drops a crucial constraint, two agents duplicate work, a supervisor mis-integrates conflicting sub-results. The overhead scales with how much the agents must coordinate — which is exactly why low-coordination task decompositions are the ones where multi-agent pays off.

### A practical decision guide

1. **Can a single agent with good tools and context engineering do it?** If yes, stop here.
2. **Do you need parallel/decomposed work but shared context?** Use orchestrator-worker in one graph.
3. **Do subtasks need genuinely isolated contexts, tools, or memory?** Now consider multi-agent.
4. **Is there a clear coordinator?** Supervisor. **Too many specialists?** Hierarchical. **Local handoff beats central routing?** Swarm. **Truly need any-to-any?** Network (reluctantly).
5. **For each handoff, specify the minimal payload.** Isolate everything else.

## Why it matters

Multi-agent is the most over-applied architecture in the field. Teams adopt it because it reads as sophisticated, then discover their token bill tripled, latency doubled, and reliability *dropped* because the seams leak. The expert stance is disciplined: multi-agent is a specific answer to a specific problem — context isolation for separable subtasks — and everything else is better served by a single well-engineered agent or an orchestrator-worker workflow. Earn the complexity.

## Pitfalls

- **Multi-agent as a first move.** It's a 15×-token, higher-latency, more-failure-prone architecture. Exhaust single-agent context engineering first.
- **Network topology by default.** Any-to-any flexibility destroys legibility and bounding. Start with supervisor.
- **Fat handoffs.** Passing full history on every handoff defeats the isolation that justified the split. Design minimal payloads.
- **Fully shared state.** Reintroduces the crowded-context problem multi-agent was meant to solve. Isolate working state; share only coordination artifacts.
- **Ignoring the seams.** Most multi-agent failures live in the handoffs, not the agents. Trace and evaluate the boundaries specifically (`08-evaluation-driven-development.md`).

## Exercises

1. Take a multi-agent design you're tempted by and rewrite it as a single agent with an orchestrator-worker section. List what you actually lose — be specific about which subtasks need isolated context, tools, or memory.
2. Implement a supervisor over two specialist agents using `Command(goto=...)` handoffs. For each handoff, write down the minimal payload and justify each field.
3. Estimate the token cost of your multi-agent design vs. the single-agent alternative on a representative task. Decide whether the isolation benefit justifies it.
4. Design the state boundaries for a supervisor system: which channels are per-agent-isolated, which are shared, and why.

## Further reading

- Context Engineering for Agents (isolation via sub-agents, the 15× figure): https://blog.langchain.com/context-engineering-for-agents/
- Anthropic — building a multi-agent research system: https://www.anthropic.com/engineering/built-multi-agent-research-system
- `langgraph-supervisor`: https://github.com/langchain-ai/langgraph-supervisor-py
- `langgraph-swarm`: https://github.com/langchain-ai/langgraph-swarm-py
- Command / handoffs (Graph API): https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph track: `docs/02-langgraph/09-subgraphs.md`, `10-multi-agent-architectures.md`
