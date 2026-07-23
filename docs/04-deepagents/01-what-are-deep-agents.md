# 01 · What Are Deep Agents

## Mental model

A "shallow" agent is the architecture you already know from the LangChain track: a model runs in a loop, calls tools, appends the results to the message list, and repeats until it stops calling tools. That loop is genuinely all you need for short tasks — answer a question, look something up, fill in a form. It starts to fail the moment the task runs *long*: dozens of tool calls, a plan that has to survive many steps, tool outputs large enough to crowd out the original instructions.

A **deep agent** is the same loop with four additions bolted on, each one a direct response to a way the shallow loop breaks down over a long horizon:

1. **A detailed system prompt** — long, example-laden instructions on how to behave, inspired by the recreated Claude Code system prompt. Prompting still matters, and the best long-horizon agents have elaborate prompts, not terse ones.
2. **A planning tool** (`write_todos`) — lets the agent write and rewrite an explicit todo list. Remarkably, the tool is essentially a no-op: it does not execute anything. Its entire value is keeping the plan in the model's context so the agent stays on track.
3. **Sub-agents** — the agent can spawn specialized child agents (via a `task` tool) that do a chunk of work in their *own* context window and hand back only the result. This quarantines noisy intermediate work away from the main thread.
4. **A virtual filesystem** — state-backed `ls` / `read_file` / `write_file` / `edit_file` tools that let the agent offload information to "files" instead of holding everything in the message history.

Harrison Chase's framing is worth memorizing: *"The core algorithm is actually the same — it's an LLM running in a loop calling tools."* Deep agents are not a new runtime. They are a **context-engineering discipline** wrapped around the ordinary loop.

```
shallow agent:   model ⇄ tools, everything lives in one growing message list
deep agent:      model ⇄ tools + [plan in context] + [sub-agent context isolation] + [files as external memory] + [big prompt]
```

## In depth

`deepagents` is a Python package (`pip install deepagents`) from LangChain, built directly on top of LangGraph. It ships a general-purpose deep agent you customize, rather than a framework you assemble. The single most important entry point:

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[my_custom_tool],
    system_prompt="You are a research assistant.",
)

result = agent.invoke({"messages": "Research LangGraph and write a summary"})
```

The crucial fact that ties this whole track to the LangGraph track: **`create_deep_agent` returns a compiled LangGraph graph** (`CompiledStateGraph`). Everything you learned about LangGraph applies unchanged:

- You invoke it with `{"messages": [...]}`, exactly like `create_agent` (see `01-langchain/09-agents-create-agent.md`).
- You stream from it with `.stream()` / `.stream_events()` (see `02-langgraph/08-streaming.md`).
- You add a `checkpointer` and pass a `thread_id` to get durable, resumable conversations (see `02-langgraph/05-persistence-checkpointers.md`).
- You get human-in-the-loop interrupts for free (see `02-langgraph/07-human-in-the-loop-interrupts.md`).
- Sub-agents are implemented as LangGraph subgraphs (see `02-langgraph/09-subgraphs.md` and `02-langgraph/10-multi-agent-architectures.md`).

So a deep agent is not an alternative to LangGraph — it *is* a LangGraph graph, assembled for you out of a stack of middleware plus a large system prompt. File `06-implementing-a-deep-agent.md` reconstructs that assembly in detail.

The (abbreviated) signature, which the rest of this track unpacks:

```python
create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None,
    skills: list[str] | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    state_schema: type[DeepAgentState] | None = None,
    context_schema: type | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    name: str | None = None,
    ...
) -> CompiledStateGraph
```

Note a naming point that trips up readers of older tutorials: early versions of `deepagents` used an `instructions=` parameter. Current versions use `system_prompt=` (the value is injected as custom instructions *inside* the larger built-in prompt). If you see `instructions=` in a blog post, mentally translate it.

### When to use what

Three tiers, from least to most machinery:

- **`create_agent`** (LangChain) — a single agent, a bounded task, a handful of tools. If the whole job fits in one context window and finishes in a reasonable number of steps, stop here. You get middleware for the customization you probably actually need without any of the deep-agent overhead.
- **`create_deep_agent`** (deepagents) — long-horizon tasks: deep research, multi-file coding, anything where the agent must plan, where intermediate work would otherwise flood the context, or where you want specialized sub-agents. Reach here when a plain `create_agent` loop starts losing the thread halfway through.
- **Raw `StateGraph`** (LangGraph) — when your control flow is genuinely bespoke: custom branching, parallel fan-out you want to orchestrate yourself, cyclic reasoning that doesn't map onto "plan + delegate + write files." Deep agents give you one strong opinion about long-horizon structure; drop to `StateGraph` when that opinion doesn't fit.

The progression mirrors the foundations mental model (`00-foundations/01-overview-and-mental-model.md`): abstraction and convenience at the top, control and expressiveness at the bottom. Start high, descend only when you hit a wall.

## Why it matters

The instinct when a long task fails is to reach for a bigger model or a bigger context window. Deep agents encode the harder-won lesson: **the context window is the scarce resource, and how you manage it determines whether long tasks succeed.** A plan kept in context, sub-agents that keep noise out of the main thread, and files that hold state outside the message list are all moves in the same game — spend the context budget on what the model needs *right now*, and park everything else. Learning deep agents is really learning context engineering with a good default implementation attached.

It also matters that this is a thin, honest layer. Because a deep agent is just a compiled LangGraph graph, you are never trapped: you can inspect it, swap its checkpointer, add your own middleware, or eventually rebuild it yourself. There is no magic to reverse-engineer later.

## Pitfalls

- **Reaching for deepagents when `create_agent` would do.** Deep agents add prompt length, extra tools, and delegation machinery. On a short task that overhead is pure cost — more tokens, more ways to go sideways. Use the shallow loop until it visibly fails.
- **Thinking it's a different runtime.** It is a LangGraph graph. If you catch yourself asking "how do I add persistence/streaming/HITL to a deep agent," the answer is always "the same way you do for any LangGraph graph."
- **Expecting the planning tool to *do* something.** `write_todos` is a no-op by design. If you are looking for where the todos get "executed," stop — the point is that they sit in context.
- **Copying `instructions=` from old posts.** The current parameter is `system_prompt=`.

## Exercises

1. Take a task that a plain `create_agent` loop handles poorly (e.g. "research three competitors and write a comparison"). List which of the four pillars — prompt, planning, sub-agents, filesystem — you expect to help most, and why.
2. Build the minimal agent from the "In depth" section and invoke it. Then inspect the object it returns and confirm it is a `CompiledStateGraph` — the same type `create_agent` produces.
3. Write one sentence each on when you would choose `create_agent`, `create_deep_agent`, and a raw `StateGraph`. Compare your answers to the tiers above.

## Further reading

- Deep Agents overview: https://docs.langchain.com/oss/python/deepagents/overview
- "Deep Agents" (LangChain blog, the announcement): https://blog.langchain.com/deep-agents/
- deepagents repository: https://github.com/langchain-ai/deepagents
- LangChain `create_agent`: https://docs.langchain.com/oss/python/langchain/agents
