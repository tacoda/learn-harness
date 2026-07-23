# 03 · Context Engineering

## Mental model

The scarce resource is the context window. Not the model, not the tools — the finite budget of tokens that reaches the model on each step. LangChain's own position is blunt: **the number one reason agents fail is that the right context was not passed to the model.** More often than model incapability. So "context engineering" — "providing the right information and tools in the right format so the LLM can accomplish a task" — is, in their words, "the number one job of AI Engineers."

The mental shift: stop thinking about the *whole conversation* and start thinking about *what reaches the model this step*. Every super-step you get to decide anew what fills the window. LangChain frames the strategies as four verbs:

- **Write** — save context outside the window (scratchpad, memory, files) so it isn't lost when it isn't needed.
- **Select** — pull the *relevant* subset back in (retrieval, memory selection, tool selection).
- **Compress** — retain only the tokens that matter (summarization, truncation).
- **Isolate** — split context across boundaries (sub-agents, sandboxes, structured state) so no single window carries everything.

Loop 1 (the agent loop) runs; context engineering decides what the loop *sees* each turn. This is the highest-leverage skill in the whole track.

## In depth

### What actually reaches the model each step

On every model call inside the loop, the input is assembled from: the system prompt, the message history (`messages` in state), the tool schemas, and any structured-output schema. Every one of those is a lever. LangChain's `create_agent` is, in their framing, "uniquely designed to facilitate context engineering" because middleware lets you rewrite each of these *per call* without forking the loop. The key distinction:

- **Transient updates** (`wrap_model_call`) change what the model sees *for one call* without touching state. Use for injecting dynamic instructions, trimming for this call only, selecting a response format.
- **Persistent updates** (`before_model`, `after_model`, returning a `Command`) modify state itself. Use when the change should stick — summarizing history down permanently, pruning consumed data.

Getting this distinction right is most of context-engineering craft: prefer transient shaping unless the change should survive to future turns.

### Compress: trimming and summarization

The default failure of a long-running agent is context overflow — each tool round appends output until the window is full. Two compression tools:

**Trimming** keeps a recent window and drops old messages (transiently, per call, or persistently in `before_model`). Cheap, lossy, no extra model call.

**Summarization** replaces old messages with an LLM-generated summary — the "auto-compact" pattern you've seen in Claude Code. LangChain ships it as middleware:

```python
from langchain.agents.middleware import SummarizationMiddleware

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[...],
    middleware=[SummarizationMiddleware(
        model="anthropic:claude-haiku-4-5",   # cheaper model does the summarizing
        trigger={"tokens": 4000},
        keep={"messages": 20},
    )],
)
```

When the conversation crosses the token trigger, older messages are summarized (by a cheaper model), replaced *permanently* in state, and recent messages kept intact. Note the cost lever: summarize with a cheap model, not the strong one. See `docs/01-langchain/08-memory-and-chat-history.md` and the short-term-memory docs.

### Compress: tool-result truncation

Tool outputs are the biggest uncontrolled source of context bloat — a database query or web fetch can return tens of thousands of tokens the model doesn't need. Truncate at the source: have the tool return a bounded, structured summary, or wrap it in `wrap_tool_call` middleware that clips the result before it enters state. A tool that returns "here are the top 5 of 4,000 rows" is doing context engineering; one that returns all 4,000 is sabotaging it.

### Select: retrieval as context injection

RAG is context engineering by another name: instead of putting a corpus in the prompt, you *select* the relevant slice at query time and inject it. The expert move is treating retrieval as a *step in the loop* — a retrieval node, or a retrieval tool the agent calls when it decides it needs facts — rather than a fixed prefix stuffed into every prompt. Select narrowly; retrieved documents are pure context cost. See `docs/01-langchain/06-retrieval-embeddings-vectorstores.md` and `07-rag-patterns.md`.

### Select: memory

Long-term memory is "write" (persist facts to a Store across threads) plus "select" (pull the *relevant* memories back in). LangChain distinguishes episodic memories (few-shot examples of desired behavior), procedural memories (instructions), and semantic facts. The selection problem is real: pull too many memories and you've just re-created the overflow you were avoiding. See `docs/02-langgraph/06-memory-short-and-long-term.md`.

### Select: tool selection

Too many tools overwhelms the model — each tool schema is context, and a long tool list degrades tool-choice accuracy. When an agent has dozens of tools, select a relevant subset per call with `LLMToolSelectorMiddleware` (a cheap model picks which tools to expose) rather than presenting all of them every step.

### Write: the filesystem / scratchpad pattern

A scratchpad is context written *outside* the window and read back on demand. It can be a tool ("write_note", "read_note") the agent calls, or a slice of runtime state the developer selectively exposes. The filesystem variant — an agent that reads and writes files as its working memory — lets an agent operate over far more information than fits in a window, paging pieces in as needed. This is the pattern deepagents formalizes (`docs/04-deepagents/01-what-are-deep-agents.md`): plan to a todo file, offload intermediate work to the filesystem, keep the window lean.

### Isolate: sub-agent context isolation

The most powerful isolation technique is splitting context across sub-agents, each with its own window, tools, and instructions. Anthropic's multi-agent researcher is the canonical case: subagents "operate in parallel with their own context windows, exploring different aspects of the question simultaneously," and many narrow contexts outperformed one crowded context. The cost is real — Anthropic reported multi-agent using up to **15× the tokens** of chat — which is exactly why `05-multi-agent-system-design.md` warns against reaching for it too early. Isolation is a context strategy with a token bill.

### Isolate: structured state vs raw messages

Not everything belongs in the message stream. A plan, a set of retrieved IDs, a running tally — these are better held as *typed state channels* the model reads selectively than as ever-growing chat turns. Structured state is context you can select from precisely; raw message history is context you can only trim bluntly. Push durable working data into named state channels and expose only what each step needs — this is where context engineering and graph engineering (`02-graph-engineering.md`) meet.

## Why it matters

Two agents with the same model and tools can differ wildly in reliability, and the difference is almost always context engineering. The team's guidance is explicit: start with static prompts and tools, add dynamics only when needed, add one context feature at a time, and *monitor model calls, token usage, and latency* as you go — because every context decision is also a cost and latency decision (`07-cost-and-latency-optimization.md`). Context engineering is not a trick; it is the primary craft of building reliable agents.

## Pitfalls

- **Stuffing everything in the prompt.** A giant static system prompt and a full tool list feels safe and is the single most common cause of poor tool choice and overflow.
- **Never compressing.** Long-running agents overflow the window unless you trim or summarize. Add `SummarizationMiddleware` before you need it.
- **Untruncated tool results.** One verbose tool can blow the budget in a single turn. Bound outputs at the tool.
- **Confusing transient and persistent updates.** Trimming persistently when you meant per-call permanently deletes history; shaping transiently when you meant to persist loses the change next turn.
- **Reaching for multi-agent isolation as a first move.** It's a legitimate context strategy but a 15×-token one; exhaust single-agent context engineering first.
- **Selecting too much.** Retrieval and memory that return everything relevant re-create the overflow problem. Narrow the selection.

## Exercises

1. Instrument an agent in LangSmith and read the token count of the model input on each step across a long run. Identify which context source (history, tool results, tool schemas) grows fastest, then apply the matching strategy (compress, truncate, select).
2. Add `SummarizationMiddleware` with a cheap summarizer model and confirm in a trace that old messages are replaced by a summary once the trigger fires.
3. Take a tool that can return large output and rewrite it to return a bounded structured summary. Measure the token delta on the following model call.
4. Map a system you've built onto the write/select/compress/isolate framing. Name at least one technique you are *not* using and decide whether you should be.

## Further reading

- Context engineering in agents (LangChain docs): https://docs.langchain.com/oss/python/langchain/context-engineering
- Context Engineering for Agents (write/select/compress/isolate): https://blog.langchain.com/context-engineering-for-agents/
- The rise of "context engineering": https://blog.langchain.com/the-rise-of-context-engineering/
- Short-term memory (trimming, summarization): https://docs.langchain.com/oss/python/langchain/short-term-memory
- Anthropic — building a multi-agent research system: https://www.anthropic.com/engineering/built-multi-agent-research-system
