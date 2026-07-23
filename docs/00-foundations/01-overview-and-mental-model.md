# 01 · Overview & Mental Model

## Mental model

Hold these four boxes in your head, from lowest to highest level:

```
                  deepagents        ← opinionated long-horizon agents (planning, subagents, FS)
                      │  built on
                  LangGraph          ← runtime: stateful graphs, persistence, durability, HITL
                      │  create_agent compiles to a graph
                  LangChain          ← building blocks: models, tools, retrieval, prompts + create_agent
                      │  emits traces / runs evals via
                  LangSmith          ← observability + evaluation plane (cross-cuts all layers)
```

- **LangChain** gives you *provider-agnostic building blocks* (a `ChatModel` interface, tools, retrievers, prompts) and a batteries-included agent constructor, `create_agent`. Reach here first for anything single-agent.
- **LangGraph** is the *runtime underneath*. When your control flow stops being "call model → maybe call tools → repeat" and becomes branching, cyclic, multi-actor, resumable, or human-gated, you drop down to `StateGraph`. `create_agent` itself compiles down to a LangGraph graph — so learning LangGraph is learning what your agent actually *is*.
- **deepagents** is an *opinionated layer on top of LangGraph* for agents that run long: they plan with a todo list, spawn sub-agents to keep context clean, and read/write a virtual filesystem. It encodes patterns you'd otherwise hand-build.
- **LangSmith** is orthogonal. It observes and evaluates *any* of the above via tracing and datasets. It is not in the request path (mostly) — it's the feedback loop that tells you whether your system actually works.

## Why three (four) libraries and not one

The split is deliberate and worth internalizing, because it dictates *where you make changes*:

- **Abstraction vs. control.** LangChain optimizes for "get a working agent in five lines." LangGraph optimizes for "express exactly the control flow and state I need." You will constantly trade between them. The mature move is to start with `create_agent` and only descend to `StateGraph` when you hit a wall the high-level API can't express (custom loops, parallel fan-out, cyclic reasoning, fine-grained interrupts).
- **Runtime vs. building blocks.** State, persistence, durability, and streaming live in LangGraph because they're *execution* concerns. Models, tools, and retrieval live in LangChain because they're *composition* concerns.
- **Dev-time vs. run-time.** LangSmith is a separate plane so that observability and evaluation don't couple to your framework choice — you can trace an app that uses none of the above.

## The v1 break (read this before any older tutorial)

The 0.x era of LangChain revolved around `Chain` classes, `LLMChain`, `AgentExecutor`, and the "LCEL everywhere" style. **LangChain 1.0 reorganized around agents.** Key deltas:

| You'll see in old tutorials | Current (v1) equivalent |
|---|---|
| `AgentExecutor`, `initialize_agent` | `langchain.agents.create_agent` |
| `langgraph.prebuilt.create_react_agent` | still exists, but `create_agent` is the new standard (adds middleware) |
| `LLMChain`, `ConversationChain` | compose a prompt \| model \| parser as a `Runnable`, or use an agent |
| Callback-based memory classes | LangGraph checkpointers + `thread_id` |
| `response_format` as a raw dict hack | `create_agent(..., response_format=ToolStrategy(MyModel))` |

If a tutorial imports `AgentExecutor`, it predates the model you should be learning. Use it for concepts, not code.

## Where you'll spend your time as you get expert

Novices spend time on "how do I call a model / add a tool." Experts spend time on:

- **State design** — what's in the graph state, how it's reduced, what's ephemeral vs. persisted.
- **Context engineering** — what actually reaches the model's context window on each step, and how to keep it small and relevant.
- **Control flow** — loops, branches, parallelism, interrupts, and recovery.
- **Evaluation** — turning "seems fine" into a dataset + evaluators + experiments that gate changes.

This course front-loads the mechanics so you can get to those four things.

## Pitfalls

- **Reaching for LangGraph too early.** If `create_agent` fits, use it — you get less code to maintain and middleware for the customization you probably actually need.
- **Treating LangSmith as optional.** Without tracing you are debugging agents blind; without evals you are shipping on vibes. Wire it in from day one.
- **Copying 0.x code.** The single biggest source of confusion is stale tutorials. Always check the import paths against v1.

## Exercises

1. In one sentence each, state when you'd choose `create_agent` vs. raw `StateGraph` vs. deepagents.
2. Explain to a colleague why LangSmith is a separate library rather than a LangChain module.
3. Find a LangChain tutorial online and identify one API in it that is now outdated.

## Further reading

- LangChain v1 release notes: https://docs.langchain.com/oss/python/releases/langchain-v1
- LangChain conceptual docs: https://docs.langchain.com/oss/python/langchain/overview
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangSmith overview: https://docs.langchain.com/langsmith/home
