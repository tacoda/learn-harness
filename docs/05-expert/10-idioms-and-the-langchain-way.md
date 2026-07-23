# 10 · Idioms & the LangChain Way

## Mental model

Every framework encodes opinions, and you get more out of it by running *with* the grain than against it. The foundations track introduced the LangChain team's core idioms (`docs/00-foundations/04-the-langchain-way-philosophy.md`); this chapter is the expert-level version — not just *what* the idioms are, but *why the team designed around them*, and the concrete gap between how beginners use the stack and how experienced practitioners do. The one-line version, unchanged: **compose small standard pieces, keep provider choice soft, start high-level and descend only when forced, express memory as state, and make everything observable and evaluable.**

The meta-idiom underneath all of them is **earn your complexity.** The framework is built so the simple thing is the default and every step toward complexity — descending to `StateGraph`, splitting into multi-agent, hand-rolling persistence — is a deliberate cost you justify, not a badge you collect. Beginners reach for the advanced tool because it looks like expertise. Experts reach for the *least* machinery that solves the problem, because they know complexity is where reliability goes to die.

## In depth

### Provider-agnostic via `init_chat_model`

The idiom: depend on the *interface*, not the vendor. `init_chat_model("anthropic:claude-sonnet-4-6")` makes the model a config string, so swapping providers, A/B-ing two, or tiering cheap-vs-strong (`07-cost-and-latency-optimization.md`) is a one-line change. **Beginner:** hard-code `ChatOpenAI(...)` throughout. **Expert:** the model is a parameter; reach for a concrete class only for a provider-specific constructor arg. *Why the team built it:* the whole package split (`docs/00-foundations/03-the-langchain-ecosystem.md`) exists to isolate your logic from any one provider — this idiom is that architecture surfacing in your code.

### Everything is a Runnable / composability

The idiom: models, tools, prompts, parsers, and whole graphs share one interface, so `|` composition and `RunnableParallel` replace bespoke glue. **Beginner:** writes imperative plumbing to pass output from one call to the next. **Expert:** composes Runnables and lets the interface carry batch, async, streaming, and tracing for free. *Why:* one uniform contract is what makes the ecosystem extensible without a combinatorial explosion of adapters (`09-library-internals.md`).

### Start simple, then descend

The idiom: there's a ladder — `create_agent` → middleware → custom `StateGraph` → functional API — and you climb *down* a rung only when the rung above genuinely can't express what you need. The team's own context-engineering guidance echoes it: "start simple, begin with static prompts and tools, add dynamics only when needed, test incrementally." **Beginner:** starts with a hand-built multi-node `StateGraph` because tutorials showed graphs. **Expert:** starts with `create_agent`, adds a piece of middleware when they need to customize, and can articulate the specific wall that forced a descent to `StateGraph` (`02-graph-engineering.md`). *Why:* most "I need LangGraph" moments are really "I need one middleware," and the higher rung is less code to maintain and get wrong.

### State + reducers over ad-hoc memory

The idiom: application memory isn't a bolt-on class — it's *state* in a graph, merged by *reducers*, persisted by a *checkpointer*, scoped by `thread_id`. The v0.x `ConversationBufferMemory` mental model is gone. **Beginner:** looks for a "memory object" to attach. **Expert:** models what to remember as state channels with deliberate reducers (`02-graph-engineering.md`), and knows short-term memory is thread-scoped state while long-term memory is the cross-thread Store (`docs/02-langgraph/06-memory-short-and-long-term.md`). *Why:* framing memory as state means persistence, resumption, HITL, and time travel all come for free from the same machinery.

### Checkpointers over custom persistence

The idiom: don't invent a "save the conversation to a row" scheme — a checkpointer gives persistence, resumption, HITL, and time travel because state is saved at every super-step (`09-library-internals.md`). **Beginner:** serializes messages to their own database table and reloads them manually. **Expert:** attaches `PostgresSaver` and gets durability, recovery, and human-in-the-loop as consequences (`06-production-reliability.md`). *Why:* custom persistence throws away everything the super-step boundary gives you and reimplements a worse version.

### Middleware over forking

The idiom: to trim context, inject a dynamic prompt, add a guardrail, or gate a tool behind approval, write **middleware** — don't fork the agent loop into a hand-rolled graph. **Beginner:** copies the ReAct loop into a custom graph to change one thing. **Expert:** writes a `before_model` / `wrap_tool_call` middleware and stays on the high-level path (`docs/01-langchain/10-middleware.md`). *Why:* middleware composes and preserves the maintained loop; forking makes you the maintainer of a loop LangChain already maintains.

### Trace everything, evaluate everything

The idiom: observability and evaluation are how you *develop*, not a later phase. Turn on `LANGSMITH_TRACING` from day one; build datasets from real traces; gate changes with evals (`08-evaluation-driven-development.md`). **Beginner:** debugs by adding print statements and ships on spot-checks. **Expert:** reads the trace tree to see what each abstraction did, and treats the build→trace→eval→improve loop as the unit of work (`01-the-agent-loop-and-loop-engineering.md`, Loop 4). *Why:* agents are non-deterministic; without tracing you debug blind and without evals you ship on vibes.

### Standard message format everywhere

The idiom: roles and content blocks (`system`/`user`/`assistant`/`tool`, multimodal content) are the lingua franca across models, agents, and graphs; `{"messages": [...]}` is *the* way to invoke. **Beginner:** builds provider-specific payload dicts. **Expert:** speaks the standard message format once and it works everywhere (`docs/01-langchain/01-chat-models-and-messages.md`). *Why:* a single message model is what makes provider-agnosticism actually hold at the data layer, not just the constructor.

### Structured output over parsing free text

The idiom: prefer `response_format=SomeModel` / `with_structured_output(...)` over regexing prose — let the model fill a schema and let the framework validate it. **Beginner:** string-parses the model's answer and writes brittle extraction. **Expert:** defines a Pydantic schema and gets `result["structured_response"]` typed and validated (`docs/01-langchain/03-structured-output.md`). *Why:* parsing free text is a v0.x smell that breaks the moment phrasing shifts; schemas are a contract.

### Tools are just functions

The idiom: a typed, docstringed Python function *is* a tool (`@tool`) — the schema is inferred, the docstring is the description the model reads. **Beginner:** hand-writes JSON schemas and vague tool descriptions. **Expert:** writes small, well-named tools with descriptions treated as prompt engineering, because tool descriptions are context the model depends on (`03-context-engineering.md`, `docs/01-langchain/05-tools-and-tool-calling.md`). *Why:* the team made tools functions precisely so tool authoring is ordinary Python, not schema bureaucracy.

### The heuristic that resolves most decisions

When two ways to do something exist, prefer the one that: keeps the provider soft, stays higher on the ladder, expresses memory as state, uses structured output, and is observable. That single heuristic answers most "which API should I use?" questions before you read the details — because it's the same set of opinions the framework was designed around, and running with the grain is always less work.

## Why it matters

The idioms aren't style preferences; they're the paths of least resistance the framework was built to make cheap. Fight them and you write more code, get less (no free tracing, no free durability, no free provider-swapping), and end up maintaining machinery LangChain already maintains. Following them is not conformism — it's leverage. The experienced practitioner is recognizable precisely by *restraint*: reaching for `create_agent` before `StateGraph`, one middleware before a fork, a checkpointer before a custom table, a schema before a parser. That restraint is what keeps systems easy to change, which is the whole game.

## Pitfalls

- **Cargo-culting the advanced tool.** Multi-agent, custom `StateGraph`, functional API — reaching for these because they look expert is the beginner tell. Earn the complexity.
- **Reintroducing v0.x patterns.** Memory classes, `AgentExecutor`, string parsing, hand-written JSON schemas — old tutorials teach them; they fight the current grain.
- **Hard-coding a provider.** Kills the one-line swap and the tiering lever. Use `init_chat_model`.
- **Custom persistence.** Reimplements a worse checkpointer and forfeits HITL and time travel.
- **Forking the loop for a small change.** Use middleware; stay on the maintained path.
- **Deferring tracing "until later."** You debug blind and it never gets added.

## Exercises

1. For each of the ten idioms, write the specific "beginner move" it corrects and one concrete cost of ignoring it in a system you've built.
2. Take a v0.x-style tutorial (memory class, `AgentExecutor`, string parsing) and rewrite it to follow the ladder, state-as-memory, and structured-output idioms. Note how much code disappears.
3. Articulate — in one sentence you'd defend in review — your personal rule for when to descend from `create_agent` to `StateGraph`.
4. Audit a system you own against the resolving heuristic (soft provider, high on the ladder, memory as state, structured output, observable). Find one place it violates the grain and fix it.

## Further reading

- The LangChain Way — philosophy & idioms: `docs/00-foundations/04-the-langchain-way-philosophy.md`
- Agents (Model + Harness, start-simple framing): https://docs.langchain.com/oss/python/langchain/agents
- Context engineering (best practices: start simple, add incrementally): https://docs.langchain.com/oss/python/langchain/context-engineering
- How to think about agent frameworks: https://blog.langchain.com/how-to-think-about-agent-frameworks/
- LangChain v1 conceptual overview: https://docs.langchain.com/oss/python/langchain/overview
