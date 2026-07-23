# 06 · Implementing a Deep Agent (Internals)

## Mental model

Strip away the branding and a deep agent is three things stacked together:

```
   a big system prompt        (tells the model how to behave over a long horizon)
 + a stack of middleware       (adds the planning/filesystem/delegation tools and manages context)
 + a compiled LangGraph agent   (the ordinary model⇄tools loop underneath)
 ─────────────────────────────
 = create_deep_agent(...)
```

That's the whole trick. There is no secret runtime. `create_deep_agent` is, in essence, a call to LangChain's `create_agent` (which compiles to a LangGraph graph) with a carefully chosen prompt and a pre-built middleware stack wired in. Harrison Chase built the first version "over a weekend" precisely because it is an *assembly* of existing LangGraph primitives, not a new engine. Understanding this is what frees you: once you see the recipe, you can extend it, debug it, or reimplement it.

The four pillars from file 01 map one-to-one onto pieces of this assembly:

| Pillar | Implemented by |
|---|---|
| Detailed system prompt | a large built-in prompt string (Claude-Code-inspired, generalized) that middleware augments |
| Planning / todos | `TodoListMiddleware` → the `write_todos` tool + prompt instructions |
| Virtual filesystem | `FilesystemMiddleware` → `ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` over a pluggable backend |
| Sub-agents | `SubAgentMiddleware` → the `task` tool that invokes child subgraphs |

## In depth

### The default middleware stack

`create_deep_agent` assembles the main agent from this stack, in order:

1. **`TodoListMiddleware`** — adds `write_todos` and appends planning instructions to the prompt. The tool is a no-op that writes the todo list into state (file 02).
2. **`SkillsMiddleware`** — surfaces skill metadata so the agent can load reusable behaviors on demand.
3. **`FilesystemMiddleware`** — adds the filesystem tools over the configured backend (`StateBackend` by default) and can enforce permissions (file 04).
4. **`SubAgentMiddleware`** — adds the `task` delegation tool and knows how to compile and invoke each configured sub-agent as its own subgraph (file 03).
5. **`SummarizationMiddleware`** — compresses long message threads automatically, a context-management move layered on top of the pillars.
6. **`PatchToolCallsMiddleware`** — repairs malformed tool calls so a single bad call doesn't derail a long run.

Custom middleware you pass via `middleware=` is inserted *after* `PatchToolCallsMiddleware`. Each piece is an ordinary `AgentMiddleware` — the same interface from `01-langchain/10-middleware.md`. Middleware is how a tool *and* its prompt instructions travel together: `TodoListMiddleware` doesn't just register `write_todos`, it also tells the model, in the system prompt, when and how to use it. That coupling is the key implementation idea — a capability is a tool plus the words that teach the model to use it.

### Sub-agents are subgraphs, and they get a trimmed stack

When you declare a sub-agent, `create_deep_agent` builds it with essentially the same stack **minus `SubAgentMiddleware`** — a sub-agent still plans, uses files, summarizes, and patches tool calls, but by default it cannot spawn further sub-agents (which keeps the delegation tree shallow and predictable). Skills run in a slightly different position in the sub-agent stack. If a declarative sub-agent sets its own `interrupt_on`, that setting is forwarded down to the `create_agent` call that builds it, so human-in-the-loop works at any level of the tree. This is a textbook use of LangGraph subgraphs (`02-langgraph/09-subgraphs.md`): each sub-agent is a self-contained compiled graph invoked from a tool in the parent.

### State: where everything lives

Deep agents extend the base agent state (`DeepAgentState`, overridable via `state_schema`). Beyond the usual `messages`, the state carries:

- the **todo list** written by `write_todos`, and
- the **`files`** dictionary that the default `StateBackend` uses as its virtual filesystem.

Because these are just state channels, they inherit LangGraph's state machinery wholesale (`02-langgraph/02-stategraph-state-and-reducers.md`): they are checkpointed, they persist across turns on a `thread_id`, and you can read them out of the returned state. "Files persist across turns" is not a filesystem feature — it's the checkpointer persisting state, which the files happen to live in.

### Reconstructing the pattern conceptually

If you were to hand-build a deep agent from LangGraph primitives, the recipe is:

1. Start from `create_agent` (or a `StateGraph` with a model⇄tools loop).
2. Extend the state schema with a `todos` channel and a `files` dict.
3. Write a no-op `write_todos` tool that updates `todos`, and a prompt fragment teaching the model to plan with it.
4. Write filesystem tools (`ls`/`read_file`/`write_file`/`edit_file`) that read and mutate the `files` dict, and a prompt fragment teaching the model to offload to them.
5. Write a `task` tool that compiles a named sub-agent (itself a `create_agent` subgraph), invokes it on a fresh message list, and returns *only* its final output — plus a prompt fragment teaching the model when to delegate.
6. Wrap steps 3–5 as middleware so each tool's instructions ride along with it, and prepend a long, example-rich system prompt.
7. Compile. Attach a checkpointer, and you have persistence, streaming, and interrupts for free.

Do this and you have re-derived `deepagents`. The point of the exercise is not to actually reimplement it — it's to internalize that the library is a *composition*, so nothing about it is opaque.

### Build your own vs. use the library

Use the library when the four pillars, as designed, fit your problem — which is most long-horizon research and coding tasks. You get a battle-tested prompt, sensible defaults, pluggable backends, and upstream maintenance for free.

Build your own harness (dropping to raw `StateGraph`, per `00-foundations/01-overview-and-mental-model.md`) when:

- your control flow genuinely diverges from "plan → delegate → write files" (e.g. a fixed pipeline, complex parallel fan-out you want to orchestrate explicitly, or cyclic reasoning that isn't delegation);
- you need a fundamentally different state shape or a planning/memory model the middleware doesn't express; or
- you want to borrow *some* pillars (say, the filesystem middleware) into an otherwise custom graph — which you can, because they're just middleware you can add to any `create_agent`.

The mature position: reach for `create_deep_agent` first, understand that it's assembled from parts you already know, and descend to hand-assembly only when a pillar actively gets in your way. Because the library and your custom graph are made of the same LangGraph primitives, the migration path in either direction is short.

## Why it matters

Knowing the internals converts the library from a black box into a starting point. When a long run misbehaves, you know *which layer* to look at: drifting off-task → planning/prompt; context bloat → filesystem/summarization; a sub-agent returning garbage → its isolated stack and system prompt; a mangled tool call → `PatchToolCallsMiddleware`. And when the defaults don't fit, you know exactly which middleware to add, replace, or drop — because you can see that a deep agent was never more than a prompt, a middleware stack, and a compiled graph.

## Pitfalls

- **Treating it as un-inspectable.** It compiles to a `CompiledStateGraph` like any other; you can print its structure, stream its internals, and read its state. Debug it as the LangGraph graph it is.
- **Forgetting sub-agents can't (by default) sub-delegate.** The trimmed sub-agent stack omits `SubAgentMiddleware` on purpose. If you need nested delegation, you're now designing a custom topology.
- **Assuming custom middleware runs first.** It's appended after the built-in stack; its position relative to summarization and tool-call patching affects what it sees.
- **Reimplementing from scratch prematurely.** The library encodes a lot of prompt-engineering and edge-case handling. Rebuild only when a pillar genuinely blocks you — not because "it's just a few middleware."

## Exercises

1. Create a deep agent and inspect the compiled graph — its nodes and the tools it exposes. Confirm you can see the built-in tools (`write_todos`, the filesystem tools, `task`) alongside your own.
2. Add a custom `AgentMiddleware` that logs the message count before each model call. Observe where in the run it fires relative to summarization.
3. Sketch (or code) a minimal hand-built version: extend an agent's state with a `files` dict and add `write_file`/`read_file` tools plus a prompt fragment. Compare its behavior to the library's filesystem.
4. Take a task and decide, with written justification, whether `create_deep_agent` or a custom `StateGraph` is the right tool — and identify which specific pillar (if any) would get in your way.

## Further reading

- Deep Agents — customization (the default middleware stacks): https://docs.langchain.com/oss/python/deepagents/customization
- "Deep Agents" blog (built-in components, "hacked on over a weekend"): https://blog.langchain.com/deep-agents/
- deepagents source: https://github.com/langchain-ai/deepagents
- LangChain middleware: https://docs.langchain.com/oss/python/langchain/middleware
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/subgraphs
- open_deep_research (a real agent built on deepagents): https://github.com/langchain-ai/open_deep_research
