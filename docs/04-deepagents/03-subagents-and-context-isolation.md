# 03 · Sub-agents and Context Isolation

## Mental model

The context window is the scarce resource. Everything a long-running agent does — every tool call, every multi-kilobyte search result, every intermediate reasoning step — accumulates in one growing message list. Past a certain size the model degrades: it loses earlier instructions, gets distracted by stale detail, and pays (in tokens and latency) for context it no longer needs. This is *context bloat*, and it is the primary reason naive agents stay shallow.

Sub-agents are the fix. A sub-agent is a full agent in its own right, running in its **own context window**. The main agent delegates a chunk of work to it — "research this subtopic," "verify these claims" — and the sub-agent does whatever messy, verbose work is required, spawning tool calls and generating intermediate text in *its* context. When it finishes, it returns **only its final answer** to the parent. All the noise stays quarantined in the child; the parent's context stays clean.

```
main agent context:                          sub-agent context (isolated):
  ...plan...                                    system prompt + task
  task("research X") ──────────────────────►    50 tool calls, huge outputs,
  ◄──────────────── "here is the summary"        scratch reasoning...
  ...continues with a clean context...           returns: one tidy summary
```

The mental shift: treat context isolation as a resource-allocation decision. Delegate work whose *process* is verbose but whose *result* is compact. The parent should see the conclusion, not the sausage-making.

## In depth

Sub-agents are supplied by `SubAgentMiddleware`, which adds a `task` tool to the main agent. When the main agent wants to delegate, it calls `task(...)` with a `subagent_type` naming which sub-agent to run and a description of the work. Under the hood each sub-agent is its own compiled LangGraph subgraph (see `02-langgraph/09-subgraphs.md`), invoked with a fresh message list — which is exactly why its context is isolated from the parent's.

Every deep agent ships with a **general-purpose sub-agent** by default: a copy of the main agent (same tools, same instructions) that the model can delegate to for arbitrary work when it wants isolation without specialization. You add **custom sub-agents** through the `subagents` parameter.

### Defining a custom sub-agent

The declarative form is a dictionary:

```python
from deepagents import create_deep_agent

research_subagent = {
    "name": "research-agent",              # required: unique id, used as subagent_type in task()
    "description": (                        # required: how the MAIN agent decides to delegate here
        "Delegate in-depth research to this subagent. Give one topic at a time."
    ),
    "system_prompt": (                      # required: the subagent's own instructions
        "You are a thorough researcher. Investigate the topic and return a "
        "concise, sourced summary — not raw notes."
    ),
    "tools": [internet_search],             # optional: overrides inherited tools if provided
    "model": "anthropic:claude-haiku-4-5",  # optional: defaults to the main agent's model
    # "skills": [...],                       # optional: subagent-specific skills
}

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    subagents=[research_subagent],
)
```

The three fields that carry the design weight:

- **`name`** — the identifier the main agent passes as `subagent_type`. Also used in metadata and streaming.
- **`description`** — read by the *main* agent to decide *whether and when* to delegate. This is a routing prompt: make it specific and action-oriented ("Use for verifying factual claims," not "a helper"). Vague descriptions produce vague delegation.
- **`system_prompt`** — the sub-agent's own instructions. It does **not** inherit the main agent's prompt, so it must stand alone, including how to format the result it returns to the parent.

You can define several specialists and let the coordinator route among them:

```python
subagents = [
    {"name": "data-collector", "description": "Gathers raw data from sources",
     "system_prompt": "Collect comprehensive data on the topic", "tools": [web_search, db_query]},
    {"name": "data-analyzer", "description": "Analyzes collected data for insights",
     "system_prompt": "Analyze data and extract key insights", "tools": [stats]},
    {"name": "report-writer", "description": "Writes polished reports from analysis",
     "system_prompt": "Create professional reports from insights", "tools": [format_doc]},
]
agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    system_prompt="You coordinate analysis and reporting. Use subagents for specialized tasks.",
    subagents=subagents,
)
```

Beyond the dict form, `create_deep_agent` also accepts `CompiledSubAgent` (hand it an already-compiled graph — any LangGraph agent, not just another deep agent) and `AsyncSubAgent` (for async execution). This is the seam where deep agents compose with the rest of the LangGraph world.

### Context flows down, results flow up

Run-level context passes automatically from parent to sub-agents and their tools. If you invoke the parent with a `context_schema` and a `context=` value, a sub-agent's tools can read it via `ToolRuntime`:

```python
from dataclasses import dataclass
from langchain.tools import tool, ToolRuntime

@dataclass
class Context:
    user_id: str

@tool
def get_user_data(query: str, runtime: ToolRuntime[Context]) -> str:
    """Fetch data for the current user."""
    return f"Data for user {runtime.context.user_id}: {query}"

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    subagents=[{"name": "researcher", "description": "Researches for the current user",
                "system_prompt": "You are a research assistant.", "tools": [get_user_data]}],
    context_schema=Context,
)
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": "Look up my recent activity"}]},
    context=Context(user_id="user-123"),
)
```

What does *not* flow up is the sub-agent's message history. Only its final output returns to the parent — that is the whole point.

### The design tradeoff

Delegation is not free. Each `task` call spins up a subgraph, which costs latency and tokens, and it introduces a lossy boundary: the parent sees a summary, not the full evidence, so if the sub-agent summarizes badly the parent inherits the error without the means to catch it. The tradeoff to weigh, every time:

- **Delegate** when the process is verbose but the result is compact, when a task benefits from a specialized prompt/toolset/model, or when you want to run a self-contained investigation without polluting the main thread.
- **Don't delegate** when the work is short (the overhead dwarfs the benefit), or when the parent genuinely needs the intermediate detail to make its next decision.

The unifying principle: sub-agents spend *more total compute* to preserve the *scarcest resource*, the main agent's context window.

## Why it matters

Sub-agents are what let deep agents "go deep." A single flat context can only hold so much before quality collapses; delegation multiplies effective working memory by giving each strand of work its own window. This is the same insight behind Deep Research and coding agents that run for many minutes — they are not one enormous context, they are a coordinator plus many short-lived, isolated workers. It is also a clean example of the multi-agent architectures from the LangGraph track (`02-langgraph/10-multi-agent-architectures.md`), pre-packaged with sensible defaults.

## Pitfalls

- **Weak `description` fields.** The main agent routes on the description alone. If it is vague, the agent either won't delegate or will delegate to the wrong specialist. Write descriptions like routing rules.
- **Forgetting sub-agents don't inherit the system prompt.** Each sub-agent's `system_prompt` must be self-contained, including output-format instructions, or you'll get raw notes back instead of a clean summary.
- **Over-delegation.** Wrapping every trivial step in a `task` call multiplies latency and cost and can *hurt* results by fragmenting reasoning. Delegate chunks, not keystrokes.
- **Trusting summaries blindly.** The isolation boundary is lossy. For high-stakes work, have the sub-agent write full findings to a file (see `04-virtual-filesystem.md`) and return a summary, so the evidence survives even though it left the parent's context.

## Exercises

1. Build a coordinator with one custom `research-agent` sub-agent. Stream the run and confirm the sub-agent's many tool calls never appear in the main agent's message list — only its final summary does.
2. Take the same description field and write it two ways, vague vs. specific. Run both and observe how reliably the coordinator delegates.
3. Build the three-specialist pipeline (collector → analyzer → writer) and trace how work moves between them. Where is context saved? Where could a bad summary corrupt the final report?
4. Convert one dict-based sub-agent into a `CompiledSubAgent` by passing a separately compiled `create_agent` graph, and confirm the parent still delegates to it.

## Further reading

- Deep Agents — subagents: https://docs.langchain.com/oss/python/deepagents/subagents
- Deep Agents — context engineering: https://docs.langchain.com/oss/python/deepagents/context-engineering
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/subgraphs
- LangGraph multi-agent architectures: https://docs.langchain.com/oss/python/langchain/multi-agent
