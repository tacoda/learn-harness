# 10 · Multi-Agent Architectures

## Mental model

A single agent degrades when it has too many tools, too many responsibilities, or too much context to juggle. The fix is to split the work across several specialized agents that cooperate. Every multi-agent system is, structurally, **a graph of agents** — each agent is a subgraph (chapter 9), and the interesting design question is the *topology*: who can talk to whom, and who decides what runs next.

Four topologies cover almost everything:

- **Network** — any agent can hand off to any other. Maximum flexibility, minimum structure. Hard to reason about at scale.
- **Supervisor** — one coordinator agent routes work to specialist workers, which report back to it. A hub-and-spoke. The most common production pattern.
- **Hierarchical** — supervisors of supervisors. Teams of agents, each team led by a supervisor, all under a top-level supervisor. Supervisor, recursively.
- **Swarm** — agents hand off directly to each other and the system *remembers which agent is active*, so the conversation stays with whichever specialist the user is currently working with until someone hands off again.

The common mechanism underneath all of them is the **handoff**: one agent transferring control (and usually the shared message history) to another. Handoffs are implemented with `Command(goto=...)` — often wrapped in a **handoff tool** the model can call. Choosing a topology is choosing how constrained those handoffs are.

## In depth

### The primitive: a handoff

A handoff is a `Command` that routes to another agent and updates shared state. Hand-rolled, it's a tool that returns a `Command`:

```python
from langgraph.types import Command
from langchain_core.tools import tool


@tool
def transfer_to_researcher() -> Command:
    """Hand off to the research agent."""
    return Command(goto="researcher", graph=Command.PARENT)
```

`graph=Command.PARENT` routes in the parent graph (the multi-agent graph), so control jumps from inside one agent-subgraph to a sibling agent. Everything else — supervisor, swarm — is a convention layered on this primitive.

### Supervisor (`langgraph-supervisor`)

The `langgraph-supervisor` package builds the hub-and-spoke for you. You define specialist agents, hand them to `create_supervisor`, and it generates the coordinator plus the handoff tools automatically:

```python
from langchain.agents import create_agent
from langgraph_supervisor import create_supervisor

research_agent = create_agent(model, tools=[web_search], name="research_expert")
math_agent = create_agent(model, tools=[calculate], name="math_expert")

workflow = create_supervisor(
    agents=[research_agent, math_agent],
    model=model,
    prompt=(
        "You are a supervisor managing a research expert and a math expert. "
        "Delegate research tasks to research_expert and math to math_expert."
    ),
)
app = workflow.compile()
result = app.invoke({"messages": [{"role": "user", "content": "What is 5 + 3?"}]})
```

The supervisor model reads the conversation, calls an auto-generated handoff tool (`transfer_to_math_expert`), the worker runs, and control returns to the supervisor to decide the next step. Each agent needs a unique `name`. For explicit control over delegation, pass custom handoff tools:

```python
from langgraph_supervisor import create_handoff_tool

custom = [
    create_handoff_tool(agent_name="research_expert", name="delegate_research",
                        description="Delegate a research task to the research expert"),
    create_handoff_tool(agent_name="math_expert", name="delegate_math",
                        description="Delegate a math task to the math expert"),
]
workflow = create_supervisor(agents=[research_agent, math_agent], model=model, tools=custom)
```

The supervisor is the default choice: the routing logic lives in one place (the coordinator), workers stay simple and independent, and you can add or remove a specialist without touching the others.

One wrinkle worth knowing: `langgraph-supervisor` (0.0.31) still builds its *own* coordinator with the deprecated `langgraph.prebuilt.create_react_agent` internally. Your workers should use `create_agent`, but the package's internal call will trip `LangGraphDeprecatedSinceV10` if you run with `-W error::DeprecationWarning`. Python's default warning filter only surfaces `DeprecationWarning` raised from `__main__`, so you won't see it in a normal run — it's the library's migration to make, not yours.

### Swarm (`langgraph-swarm`)

In a swarm there is no central coordinator. Agents hand off directly to each other, and the graph tracks an `active_agent` in state so the *next* user turn resumes with whoever was last in control — not always the same entry agent. `langgraph-swarm` provides `create_swarm` and its own `create_handoff_tool`:

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_swarm import create_handoff_tool, create_swarm

alice = create_agent(
    model,
    tools=[add, create_handoff_tool(agent_name="Bob", description="Transfer to Bob")],
    system_prompt="You are Alice, an addition expert.",
    name="Alice",
)
bob = create_agent(
    model,
    tools=[create_handoff_tool(agent_name="Alice", description="Transfer to Alice, she does math")],
    system_prompt="You are Bob, you speak like a pirate.",
    name="Bob",
)

workflow = create_swarm([alice, bob], default_active_agent="Alice")
app = workflow.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": "1"}}
app.invoke({"messages": [{"role": "user", "content": "I'd like to speak to Bob"}]}, config)
app.invoke({"messages": [{"role": "user", "content": "what's 5 + 7?"}]}, config)
# Turn 2 starts with Bob (the last active agent), who hands off to Alice for the math.
```

Note two requirements: `default_active_agent` names who starts when nothing is active yet, and a **checkpointer is mandatory** for multi-turn swarms — the `active_agent` field only persists across turns if state is checkpointed. The swarm's handoff tool returns a `Command` that sets `active_agent`, routes to the target, and preserves message history.

### Hierarchical

When even a single supervisor has too many workers, group them into teams: each team is a supervisor-led subgraph, and a top-level supervisor routes between teams. Because a supervisor workflow compiles to a graph, and graphs nest as subgraphs, you build hierarchy by using one supervisor graph as a worker inside another. This scales the supervisor pattern without any new primitive.

### Network

Let every agent hand off to every other and you have a network. Build it hand-rolled with subgraphs and `Command(goto=...)` handoff tools pointing at any sibling. It's the most flexible and the least constrained — useful when interactions are genuinely unstructured, but the hardest to debug because control can go anywhere. Prefer a supervisor unless you truly need arbitrary agent-to-agent flow.

### Choosing a topology

| Topology | Coordinator? | Handoffs allowed | Choose when |
|---|---|---|---|
| Network | none | any → any | Interactions are genuinely unstructured (rare) |
| Supervisor | one central | worker ↔ supervisor | Default; clear delegation, independent specialists |
| Hierarchical | nested | within/between teams | Too many workers for one supervisor |
| Swarm | none | any → any, sticky | Users work with one specialist at a time, conversationally |

Start with a supervisor. Escalate to hierarchical when one supervisor's tool list gets unwieldy. Reach for swarm when the UX is a conversation that should "stay with" the current specialist. Use a hand-rolled network only when none of the structured patterns fit.

## Why it matters

Multi-agent design is mostly a **context-engineering** strategy. A single agent with twenty tools makes worse tool choices and burns more tokens than three focused agents with seven tools each, because each specialist sees only its relevant context. Topology is how you control which agent holds which context and when control moves. The wrong topology (a free-for-all network where a supervisor would do) turns a debuggable system into an emergent mess; the right one keeps each agent simple and each handoff legible. And since it's all graphs and `Command`, you can start hand-rolled and adopt `langgraph-supervisor`/`langgraph-swarm` later without discarding your mental model.

## Pitfalls

- **Reaching for multi-agent too early.** Many "multi-agent" problems are one `create_agent` with good tools. Split only when a single agent's context or tool set is demonstrably overloaded.
- **Swarm without a checkpointer.** `active_agent` won't persist across turns, so the swarm forgets who's in control. Compile with a checkpointer.
- **Duplicate or missing agent `name`s.** Handoff tools route by name; supervisor and swarm both require each agent to have a unique `name`, or routing breaks.
- **Uncontrolled networks.** Any-to-any handoffs are hard to reason about and easy to loop forever. Add structure (a supervisor) unless you truly need the freedom, and mind the recursion limit.
- **Losing or duplicating message history across handoffs.** Handoff tools decide whether to add handoff messages to history; misconfigure it and the receiving agent sees a garbled conversation. Understand what your handoff tool passes along.
- **Building workers with `create_react_agent`.** Deprecated since LangGraph v1.0 (removal targeted for v2.0). Build workers with `langchain.agents.create_agent`; it takes the same `model` / `tools` / `name` arguments the supervisor and swarm factories need.
- **Stale-tutorial trap.** Older multi-agent tutorials predate `langgraph-supervisor` and `langgraph-swarm` and hand-wire everything, or build workers with the old `create_react_agent` exclusively. In v1, workers are `create_agent`, and the supervisor/swarm packages provide `create_supervisor` / `create_swarm` and their handoff-tool factories.

## Exercises

1. Build a two-worker supervisor with `create_supervisor` (a search agent and a math agent). Ask a question that needs both and trace, via `stream_mode="updates"`, how control moves supervisor → worker → supervisor.
2. Build the Alice/Bob swarm with a checkpointer. Confirm that a second turn resumes with the last active agent, not the default. Remove the checkpointer and observe what breaks.
3. Hand-roll a minimal network: two agent-subgraphs, each with a handoff tool returning `Command(goto=..., graph=Command.PARENT)`. Note how much harder the control flow is to predict than the supervisor version.
4. Sketch (no code needed) a hierarchical system for a company assistant: a top supervisor over a "sales team" supervisor and a "support team" supervisor. Identify which handoffs cross team boundaries.

## Further reading

- Multi-agent overview and patterns: https://docs.langchain.com/oss/python/langgraph/multi-agent
- `langgraph-supervisor`: https://docs.langchain.com/oss/python/langgraph/multi-agent#supervisor
- `langgraph-swarm`: https://github.com/langchain-ai/langgraph-swarm-py
- Handoffs with `Command`: https://docs.langchain.com/oss/python/langgraph/multi-agent#handoffs
