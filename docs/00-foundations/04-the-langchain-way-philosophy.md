# 04 · The LangChain Way — Philosophy & Idioms

## Mental model

Every framework encodes opinions. If you fight them, you write more code and get less. This doc names the opinions the LangChain team designs *around* so that when you hit a decision, you already know which way the grain runs. The one-line version: **compose small standard pieces, keep provider choice soft, start high-level and descend only when forced, and make everything observable and evaluable.**

## The idioms, and why they exist

### 1. Provider-agnostic by default

Depend on the *interface*, not the vendor. Use `init_chat_model("claude-...")` and pass models as strings/config, so swapping providers — or A/B-ing two — is a one-line change. Reach for a concrete class (`ChatAnthropic`) only when you need a provider-specific constructor argument. **Beginner move:** hard-code `ChatOpenAI` everywhere. **Their way:** the model is a parameter.

### 2. Everything is a Runnable

Models, prompts, tools, retrievers, parsers, and whole chains all implement one interface: `.invoke / .stream / .batch` (+ async). That uniformity is *the* abstraction — it's why `prompt | model | parser` works, and why a LangGraph node can call any of them. Learn the Runnable contract once and the whole library becomes composable. Composition (`|`, `RunnableParallel`) is preferred over bespoke glue code.

### 3. Start simple, descend deliberately

There's a ladder: **`create_agent` → middleware → custom `StateGraph` → functional API**. Climb down a rung only when the rung above genuinely can't express what you need. Most "I need LangGraph" moments are actually "I need one piece of middleware." **Their way:** use the highest-level tool that fits, and treat descending as a cost you justify, not a badge you earn.

### 4. State + reducers over ad-hoc memory

Application "memory" isn't a special class you bolt on — it's *state* in a graph, merged by *reducers*, persisted by a *checkpointer*, and scoped by a *thread_id*. The v0.x `ConversationBufferMemory` mental model is gone. When you want history, you want state; when you want it to survive restarts, you want a checkpointer; when you want it across threads, you want the Store. (LangGraph track goes deep.)

### 5. Checkpointers over custom persistence

Don't invent your own "save the conversation to a row" scheme. A checkpointer gives you persistence, resumption, human-in-the-loop, and time-travel for free, because state is saved at every super-step. Custom persistence throws all of that away.

### 6. Middleware over forking

When you need to trim context, inject a dynamic system prompt, add a guardrail, or gate a tool call behind approval — write **middleware**, don't fork the agent loop into a hand-rolled graph. Middleware is the v1 answer to "I need to customize the agent *a little*." It composes and keeps you on the high-level path.

### 7. Structured output over parsing free text

Prefer `with_structured_output(MyModel)` / `response_format=ToolStrategy(MyModel)` over regexing the model's prose. Let the model fill a schema; let the framework validate it. Parsing strings is a v0.x smell.

### 8. Trace everything, evaluate everything

Observability and evaluation aren't a later phase — they're how you develop. Turn on `LANGSMITH_TRACING` from day one so you can *see* what each abstraction does, build datasets from real traces, and gate changes with evals. **Their way:** the feedback loop (build → trace → eval → improve) is the unit of work, not the single run.

### 9. Standard message format everywhere

Roles and content blocks (`system`/`user`/`assistant`/`tool`, multimodal content) are the lingua franca across models, agents, and graphs. Passing `{"messages": [...]}` is the idiom for invoking agents and graphs. Learn the message model once; it's the same everywhere.

### 10. Tools are just functions

A Python function with type hints and a docstring *is* a tool (`@tool`). The schema is inferred; the docstring is the description the model reads. You don't write JSON schemas by hand. Keep tools small, well-named, and well-described — the description is prompt engineering.

## How this changes how you read the docs

When you see two ways to do something, prefer the one that: keeps the provider soft, stays higher on the ladder, expresses memory as state, and is observable. That heuristic resolves most "which API should I use?" questions before you even read the details.

## Pitfalls

- **Cargo-culting multi-agent / LangGraph** because it looks advanced. The idiom is the opposite: earn the complexity.
- **Reintroducing v0.x patterns** (memory classes, `AgentExecutor`, string parsing) because that's what old tutorials show. They fight the current grain.
- **Skipping tracing "until later."** You'll debug blind and it never gets added.

## Exercises

1. For each of the 10 idioms, write the one-line "beginner move" it's correcting.
2. Take a v0.x tutorial and rewrite its approach to follow idioms 3, 4, and 7.
3. Articulate your personal rule for when to descend from `create_agent` to `StateGraph`.

## Further reading

- LangChain conceptual overview: https://docs.langchain.com/oss/python/langchain/overview
- Agents concept: https://docs.langchain.com/oss/python/langchain/agents
- LangChain v1 release notes: https://docs.langchain.com/oss/python/releases/langchain-v1
- LangChain blog (architecture & context-engineering essays): https://blog.langchain.com/
