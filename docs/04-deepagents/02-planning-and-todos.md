# 02 · Planning and Todos

## Mental model

The planning tool is the strangest of the four pillars, because it *does nothing*. `write_todos` takes a list of tasks and writes them into the agent's state. It runs no code, calls no external system, triggers no side effect. Harrison Chase is blunt about it in the announcement: the Claude Code todo tool "doesn't do anything! It's basically a no-op. It's just context engineering strategy to keep the agent on track."

So why include it? Because a language model has no working memory other than its context window. On a long task, the original goal and the current sub-goal drift further and further back in the message history, buried under tool outputs. The model starts to lose the plot — repeating steps, forgetting a requirement, declaring victory early. Writing an explicit todo list, and rewriting it as work progresses, keeps a compact, current statement of *what we are doing and what is left* near the front of the model's attention.

Think of it as the agent talking to its future self. Each time the loop comes back around, the most recent todo list is right there, re-anchoring the model to the plan it committed to. The plan is not executed by the framework; it is executed by the model *reading its own plan*.

```
without planning:   goal ......... 40 tool calls ......... "am I done? I think so?"
with planning:      goal → [todos] → work → [todos updated] → work → [todos updated] → done
                            ^ the list is always near the top of attention
```

## In depth

The planning tool is supplied by `TodoListMiddleware`, the first entry in the default middleware stack that `create_deep_agent` assembles. You do not import or wire it yourself — creating any deep agent gives you `write_todos` automatically, and the middleware appends usage instructions for it to the system prompt.

The todos live in the agent's LangGraph state. Because they are state, they participate in everything state does: they are checkpointed, they survive across turns on the same `thread_id`, and you can read them out of the returned state after a run. A todo item is a small record — its text and a status such as pending, in-progress, or completed. When the agent calls `write_todos`, it typically rewrites the whole list, flipping statuses and adding or removing items as its understanding evolves.

Here is the behavior you will observe when you stream a deep agent on a multi-step task:

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[search, fetch_page],
    system_prompt="You are a research assistant. Produce a sourced report.",
)

for chunk in agent.stream(
    {"messages": "Compare the three leading vector databases and recommend one."},
    stream_mode="values",
):
    # Early in the run you'll see a write_todos call laying out the plan:
    #   1. Identify the three leading vector DBs   (in_progress)
    #   2. Gather features/pricing for each        (pending)
    #   3. Compare on the user's criteria          (pending)
    #   4. Write the recommendation                (pending)
    # then repeated write_todos calls flipping items to completed as it goes.
    pass
```

You do not have to trust that this is happening. Because todos are state, you can inspect them:

```python
final_state = agent.invoke({"messages": "..."})
# The todo list is available in the returned state (alongside "messages", "files", etc.)
```

### Steering the planner

You influence planning almost entirely through the **system prompt**, because that is where the model learns what a good plan looks like for *your* domain. The built-in prompt already instructs the agent to plan; your `system_prompt` is injected as additional instructions inside it. Effective steering looks like:

- Telling the agent *when* to plan — "For any task with more than a few steps, begin by writing a todo list."
- Telling it *what a task means in your domain* — "A complete research task always includes a verification pass before writing the report."
- Telling it *how granular* todos should be — too coarse and the plan doesn't help; too fine and it becomes bookkeeping noise.
- Telling it to *keep the list current* — "Update your todos after completing each item; do not batch updates."

Because the todo list is context engineering, over-steering can backfire: a plan so detailed that maintaining it consumes more attention than the work does. The goal is a plan compact enough to re-read cheaply on every loop and precise enough to prevent drift.

Sub-agents (see `03-subagents-and-context-isolation.md`) each get their own planning tool in their own context, so delegated work can carry its own sub-plan without polluting the parent's list.

## Why it matters

Planning is the cheapest, highest-leverage of the four pillars: a no-op tool and a few lines of prompt, and long-horizon reliability improves measurably. It is the clearest demonstration of the whole deep-agents thesis — that **arranging what sits in the context window is often worth more than a bigger model.** No new capability is added; the model is simply kept oriented.

It also gives you an observability handle. The evolving todo list is a running commentary on what the agent thinks it is doing. When a long run goes wrong, the todos usually show *where* the model's understanding diverged from the task — a diagnostic you would not have with a plain tool loop.

## Pitfalls

- **Expecting execution.** `write_todos` never runs your tasks. If a todo says "call the API" the model still has to call the API tool separately. The list is a note, not a scheduler.
- **Over-prescribing the plan.** Forcing an elaborate planning ritual on short tasks wastes tokens and can derail simple work. Let the model plan when the task warrants it; steer, don't script.
- **Ignoring the todos when debugging.** People read the message transcript and skip the todo state. The todo list is frequently the fastest way to see the agent's intent go off the rails.
- **Assuming todos are shared across threads.** They live in thread-scoped state. A new `thread_id` starts with an empty plan.

## Exercises

1. Run a deep agent on a genuinely multi-step task with `stream_mode="values"` and log every `write_todos` call. Watch the plan mutate. Note the point (if any) where the plan and the actual work diverge.
2. Give the same task to a plain `create_agent` (no planning) and to a `create_deep_agent`. Compare how faithfully each covers every part of a multi-part request.
3. Write a `system_prompt` that defines what "done" means for a specific domain task, requiring a verification todo before completion. Confirm the agent adds and completes that item.
4. After a run, extract the final todo list from the returned state and render it as a human-readable checklist.

## Further reading

- Deep Agents — context engineering (planning, filesystem, subagents): https://docs.langchain.com/oss/python/deepagents/context-engineering
- "Deep Agents" blog, "Characteristics of deep agents": https://blog.langchain.com/deep-agents/
- LangGraph state and reducers (where todos live): https://docs.langchain.com/oss/python/langgraph/graph-api
