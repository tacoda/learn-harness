# 05 · Customizing and Middleware

## Mental model

`create_deep_agent` gives you an opinionated default deep agent. Customization is the art of bending that default toward your problem *without* throwing away the parts that make it deep. There are two levers, and it helps to keep them distinct:

1. **Configuration parameters** — the arguments to `create_deep_agent`: your `system_prompt`, your `tools`, your `subagents`, your `model`, your `backend`. This is how you tell the agent *what it works on*.
2. **LangGraph machinery** — `checkpointer`, `store`, `context_schema`, `interrupt_on`, and custom `middleware`. This is how you control *how it runs*: persistence, memory, per-run data, human approval, and cross-cutting behavior.

The reason lever 2 works is the fact this whole track keeps returning to: a deep agent **is a compiled LangGraph graph**. So every runtime capability from the LangChain and LangGraph tracks — middleware (`01-langchain/10-middleware.md`), checkpointers (`02-langgraph/05-persistence-checkpointers.md`), stores (`02-langgraph/06-memory-short-and-long-term.md`), interrupts (`02-langgraph/07-human-in-the-loop-interrupts.md`) — is available to a deep agent by construction. You are not learning a new customization system; you are pointing the one you already know at a graph that happens to have been assembled for you.

## In depth

### The configuration levers

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",     # any provider string or a BaseChatModel instance
    tools=[search, fetch, run_query],          # your functions, BaseTools, or MCP tools
    system_prompt="You are a financial analyst. Always cite sources and dates.",
    subagents=[research_agent, fact_checker],  # custom specialists (see file 03)
)
```

- **`system_prompt`** — injected as custom instructions *inside* the large built-in prompt. You are steering the default agent, not replacing its scaffolding. This is where domain knowledge, output conventions, and "when to plan / delegate / write files" guidance go.
- **`tools`** — plain Python callables, `BaseTool` instances, or tools from any MCP server. These come *in addition to* the built-in planning, filesystem, and delegation tools.
- **`model`** — a provider string (`"anthropic:claude-sonnet-4-5"`) or a constructed `BaseChatModel`. Sub-agents default to this model but can each override it, so you can run an expensive coordinator with cheaper specialists (or vice versa).
- **`subagents`** — covered in `03-subagents-and-context-isolation.md`.

### Persistence, memory, and per-run context

Because it's a LangGraph graph, you pass these straight through:

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    checkpointer=MemorySaver(),   # durable, resumable threads (use a DB saver in prod)
    store=InMemoryStore(),        # cross-session/long-term memory
)

config = {"configurable": {"thread_id": "conv-1"}}
agent.invoke({"messages": [{"role": "user", "content": "Plan a 3-day Tokyo trip"}]}, config=config)
agent.invoke({"messages": [{"role": "user", "content": "Make it 5 days"}]}, config=config)  # same thread continues
```

The `thread_id` scopes the conversation — message history, checkpoints, and the virtual filesystem. A `context_schema` plus a `context=` argument carries *per-run* data (user id, API keys, session metadata) that tools and middleware read at invocation time; it flows automatically to sub-agents and their tools (see file 03). These two are independent: `thread_id` is *which conversation*, `context` is *this run's inputs*.

### Human-in-the-loop, especially on file writes

Autonomy is not always appropriate. Deep agents support pausing at specific tool calls for human approval, edit, or rejection — the LangGraph interrupt mechanism (`02-langgraph/07-human-in-the-loop-interrupts.md`), surfaced through the `interrupt_on` parameter:

```python
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    checkpointer=MemorySaver(),                     # required: interrupts need to persist state
    interrupt_on={"write_file": True, "edit_file": True},
)
```

When the agent tries to call an interrupted tool, execution pauses and returns control to you. A human approves, edits the arguments, or rejects; you resume by invoking with the **same config** and a `Command(resume=...)`:

```python
from langgraph.types import Command

config = {"configurable": {"thread_id": "t-1"}}
result = agent.invoke({"messages": [{"role": "user", "content": "Update the report file"}]}, config=config)
# ... execution pauses at write_file; inspect the pending call, get a human decision ...
result = agent.invoke(Command(resume={"decision": "approve"}), config=config)  # same config
```

This matters most with a real `FilesystemBackend` (see `04-virtual-filesystem.md`): when writes hit actual disk, `write_file` and `edit_file` default to requiring approval, while `read_file` does not interrupt. A `checkpointer` is mandatory for any of this — an interrupt is only useful if the paused state can be persisted and resumed. Note that `interrupt_on` permissions apply to the built-in filesystem tools; they do not cover arbitrary custom tools or sandbox `execute` calls, which you must gate yourself.

### Custom middleware and the default stack

The deepest customization lever is middleware. `create_deep_agent` builds the agent from a default stack (detailed in `06-implementing-a-deep-agent.md`):

`TodoListMiddleware → SkillsMiddleware → FilesystemMiddleware → SubAgentMiddleware → SummarizationMiddleware → PatchToolCallsMiddleware`

Anything you pass via `middleware=` is inserted **after** `PatchToolCallsMiddleware` and before the tail of the stack. So your custom middleware layers on top of the deep-agent scaffolding rather than replacing it. This is the same `AgentMiddleware` interface from the LangChain track (`01-langchain/10-middleware.md`) — use it for guardrails, PII redaction, extra context injection, custom summarization, logging, and other cross-cutting concerns:

```python
from langchain.agents.middleware import PIIMiddleware

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    middleware=[PIIMiddleware("email")],   # runs on top of the built-in deep-agent stack
)
```

The `SummarizationMiddleware` in the default stack is worth noting: it compresses long threads automatically, a fourth context-management move on top of planning, sub-agents, and files. `skills` (reusable behaviors loaded on demand) and `permissions` (fine-grained filesystem access rules) are further configuration surfaces for advanced use.

### Async

Because the result is a LangGraph graph, the async methods work out of the box: `await agent.ainvoke(...)` and `agent.astream(...)`. For delegation, deepagents accepts `AsyncSubAgent` definitions, and the default middleware stack has async-appropriate variants — so an async coordinator can delegate to async sub-agents without you managing the concurrency by hand.

## Why it matters

Customization is where deep agents earn their keep in production. The default agent is a strong starting point, but a real deployment needs *your* tools, *your* domain prompt, durable conversations, per-user context, and a human gate on anything irreversible. The payoff of the "it's just a LangGraph graph" design is that none of this requires new concepts: you reuse checkpointers, stores, interrupts, and middleware exactly as elsewhere. The library gives you the long-horizon scaffolding; LangGraph gives you the operational controls; they compose cleanly because they are the same object.

## Pitfalls

- **Replacing instead of steering the prompt.** `system_prompt` is inserted into the built-in prompt, not swapped for it. Writing a terse replacement doesn't delete the scaffolding — and trying to fight the built-in instructions in your custom text usually just confuses the model.
- **Interrupts without a checkpointer.** `interrupt_on` needs somewhere to persist the paused state. No `checkpointer`, no working human-in-the-loop.
- **Assuming approval covers every tool.** `interrupt_on` on filesystem tools does not gate your custom tools or sandbox `execute`. Wrap those in your own approval if they're dangerous.
- **Resuming with a different config.** You must resume an interrupted run with the *same* `thread_id`/config, or the checkpointer can't find the paused state.
- **Expecting custom middleware to run first.** It's inserted after the built-in stack. If ordering matters (e.g. you need to see messages before summarization), understand where your middleware actually sits.

## Exercises

1. Add a `checkpointer` and run a two-turn conversation on one `thread_id`, confirming turn two remembers turn one. Then start a fresh `thread_id` and confirm it doesn't.
2. Configure `interrupt_on={"write_file": True}` with a `FilesystemBackend`. Trigger a write, inspect the paused call, then resume with `Command(resume=...)` to approve it. Repeat and reject it instead.
3. Write a trivial custom middleware that logs every model call, pass it via `middleware=`, and confirm it runs on top of the built-in stack without disabling planning/filesystem/delegation.
4. Convert an agent to async: run it with `await agent.ainvoke(...)` and stream with `agent.astream(...)`, and confirm behavior matches the sync version.

## Further reading

- Deep Agents — customization (middleware stack, backends, model/prompt): https://docs.langchain.com/oss/python/deepagents/customization
- Deep Agents — human-in-the-loop: https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
- Deep Agents — going to production (thread_id, context): https://docs.langchain.com/oss/python/deepagents/going-to-production
- Deep Agents — permissions: https://docs.langchain.com/oss/python/deepagents/permissions
- LangChain middleware: https://docs.langchain.com/oss/python/langchain/middleware
