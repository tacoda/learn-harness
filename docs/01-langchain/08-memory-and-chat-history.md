# 08 · Memory & Chat History

## Mental model

A chat model is **stateless** — it remembers nothing between calls. "Memory" is just the practice of storing prior messages somewhere and replaying them on the next turn. In v1, that "somewhere" is a **LangGraph checkpointer**, addressed by a **`thread_id`**. The 0.x memory classes (`ConversationBufferMemory`, `ConversationChain`, `ConversationSummaryMemory`, …) are **gone** — memory is no longer a bag of helper objects bolted onto a chain, it's a property of the graph runtime underneath your agent.

## In depth

### Short-term memory = checkpointer + thread_id

Give an agent a checkpointer and it persists its message state per thread. Reuse the `thread_id` and the prior conversation is automatically replayed:

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[],
    checkpointer=InMemorySaver(),
)

config = {"configurable": {"thread_id": "user-42-session-1"}}

agent.invoke({"messages": [{"role": "user", "content": "Hi! My name is Bob."}]}, config)
agent.invoke({"messages": [{"role": "user", "content": "What's my name?"}]}, config)
# -> "You are Bob!"  — history was reloaded from the checkpointer for this thread_id
```

Two things to internalize:
- You pass only the **new** message each turn. The checkpointer reloads the accumulated state for that `thread_id`; you don't resend history yourself.
- `thread_id` **is** the conversation identity. Same id → same conversation. Different id → a fresh, independent one. A per-user, per-session id is the usual scheme.

### Persistence backends

`InMemorySaver` is for development — state dies with the process. For production, swap in a durable checkpointer; the agent code doesn't change, only the constructor:

```python
from langgraph.checkpoint.sqlite import SqliteSaver       # local file
# from langgraph.checkpoint.postgres import PostgresSaver  # production

agent = create_agent(model="claude-sonnet-4-6", tools=[], checkpointer=SqliteSaver(conn))
```

This is the payoff of memory-as-runtime: dev/prod parity for free, and the same checkpointer also gives you time-travel and resumability (the LangGraph track).

### The context-window problem: trim and summarize

Replaying *all* history eventually overflows the context window and inflates cost linearly with conversation length. Two remedies, both operating on the message list before it reaches the model:

**Trim** — keep the last N tokens/messages, drop the oldest:

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    messages,
    max_tokens=4000,
    strategy="last",
    token_counter=model,
    include_system=True,      # never trim the system message away
)
```

**Summarize** — replace old turns with a running summary so you keep the *gist* without the tokens. In v1 this is a **middleware** you attach to the agent, not a bespoke memory class:

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[],
    checkpointer=InMemorySaver(),
    middleware=[SummarizationMiddleware(model="claude-sonnet-4-6", trigger={"tokens": 4000})],
)
```

When the thread crosses the trigger, the middleware summarizes older messages in place before the model call. Trimming is cheap and lossy on detail; summarization preserves gist at the cost of an extra model call. Module 10 covers middleware in full.

### Short-term vs. long-term

What's described here is **short-term** memory — state scoped to one thread/conversation. **Long-term** memory (facts about a user that persist *across* threads: preferences, profile) is a different mechanism — a LangGraph **Store**, keyed independently of `thread_id`. This track covers short-term; the LangGraph track covers the Store, cross-thread memory, and durable-execution details.

## Why it matters

Moving memory into the checkpointer collapses several 0.x concepts into one: conversation state, persistence, durability, and resumability are now *the same thing*, addressed by `thread_id`. You stop choosing between a dozen memory classes and instead choose a checkpointer backend and a trimming/summarization policy — two orthogonal, swappable decisions. The tradeoff is conceptual: memory now lives in the runtime layer (LangGraph), so understanding it well means understanding graph state, which is exactly why this module points forward. The upside is that "add memory" becomes "add a checkpointer," and "scale memory" becomes "swap the backend."

## Pitfalls

- **Reaching for `ConversationBufferMemory` / `ConversationChain`.** Removed in v1. Any tutorial importing them predates the model you should learn. The replacement is checkpointer + `thread_id`.
- **No checkpointer, expecting memory.** Without one, every `.invoke` is a cold start — the agent forgets instantly. Memory requires a checkpointer *and* a stable `thread_id`.
- **Reusing a `thread_id` across users.** Conversations bleed together and you leak one user's history to another. Namespace ids per user and per session.
- **Resending full history each turn.** The checkpointer already holds it. Passing the whole transcript *and* using a checkpointer double-counts messages. Send only the new turn.
- **Letting threads grow unbounded.** Cost and latency climb with every turn until you hit the context limit. Add trimming or `SummarizationMiddleware` before that happens, not after it breaks.
- **`InMemorySaver` in production.** It evaporates on restart. Use SQLite/Postgres for anything that must survive a process.
- **Confusing short-term with long-term.** `thread_id` memory is per-conversation. Cross-conversation facts need a Store — don't try to smuggle user profiles through the message list.

## Exercises

1. Build an agent with `InMemorySaver`, tell it your name on turn one, and have it recall it on turn two using the same `thread_id`.
2. Change the `thread_id` on turn two and confirm the agent has forgotten — proving `thread_id` is the conversation identity.
3. Swap `InMemorySaver` for `SqliteSaver`, restart the process, and show the conversation survives.
4. Add `SummarizationMiddleware` with a low token trigger; run a long conversation and find the summarization step in the trace.
5. Apply `trim_messages` with `include_system=True` and verify the system message is never dropped.

## Further reading

- Memory & persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- Add memory (LangGraph): https://docs.langchain.com/oss/python/langgraph/add-memory
- Summarization middleware: https://docs.langchain.com/oss/python/langchain/middleware
- v1 migration (memory changes): https://docs.langchain.com/oss/python/releases/langchain-v1
