# Learning Progress

Tracks my walk through `learn-harness`. Read docs in order; run each example alongside its module.

**Legend:** `[ ]` todo · `[~]` in progress · `[x]` done

**Current position:** _All tracks complete (00–06). Every doc read; every example run green. `examples/06-production` verified end to end: graph imports as a CompiledStateGraph, `langgraph dev` serves it, the Runs API answers, and `eval_gate.py` scores 1.00 and exits 0._

**Env status:** uv ✅ · Python 3.14 ✅ · `OPENAI_API_KEY` ✅ · `LANGSMITH_API_KEY` ✅ · `LANGSMITH_TRACING` ✅ · `LANGSMITH_PROJECT=learn-harness` ✅ · `ANTHROPIC_API_KEY` ❌ · root `.env` present

Last updated: 2026-09-15

---

## 00 · Foundations — `docs/00-foundations`
_Explain the ecosystem and set up a clean `uv` workspace._

- [x] 01 Overview and mental model
- [x] 02 Environment setup (uv)
- [x] 03 The LangChain ecosystem
- [x] 04 The LangChain way (philosophy)

## 01 · LangChain — `docs/01-langchain`
_Compose models, tools, retrieval, and agents with `create_agent` + middleware._

| # | Doc | Example |
|---|-----|---------|
| 01 | [x] Chat models and messages | [x] `01_chat_models.py` |
| 02 | [x] Prompt templates | [x] `02_prompt_templates.py` |
| 03 | [x] Structured output | [x] `03_structured_output.py` |
| 04 | [x] Runnables and LCEL | [x] `04_runnables_lcel.py` |
| 05 | [x] Tools and tool calling | [x] `05_tools_and_calling.py` |
| 06 | [x] Retrieval, embeddings, vectorstores | [x] `06_retrieval.py` |
| 07 | [x] RAG patterns | [x] `07_rag.py` |
| 08 | [x] Memory and chat history | — |
| 09 | [x] Agents (`create_agent`) | [x] `09_agent.py` |
| 10 | [x] Middleware | [x] `10_middleware.py` |
| 11 | [x] Streaming | [x] `11_streaming.py` |
| 12 | [x] Callbacks and runtime | — |
| 13 | [x] Implementing custom components | — |

## 02 · LangGraph — `docs/02-langgraph`
_Design stateful graphs, persistence, HITL, and multi-agent systems._

| # | Doc | Example |
|---|-----|---------|
| 01 | [x] Why LangGraph (mental model) | [x] `01_hello_stategraph.py` |
| 02 | [x] StateGraph: state and reducers | [x] `02_state_reducers.py` |
| 03 | [x] Nodes, edges, control flow | [x] `03_conditional_edges.py` |
| 04 | [x] Prebuilt ReAct agent | [x] `04_react_agent.py` |
| 05 | [x] Persistence (checkpointers) | [x] `05_persistence.py` |
| 06 | [x] Memory: short- and long-term | [x] `06_long_term_memory.py` |
| 07 | [x] Human-in-the-loop interrupts | [x] `07_hitl_interrupt.py` |
| 08 | [x] Streaming | [x] `08_streaming.py` |
| 09 | [x] Subgraphs | [x] `09_subgraph.py` |
| 10 | [x] Multi-agent architectures | [x] `10_multiagent_supervisor.py` |
| 11 | [x] Durable execution and time travel | — |
| 12 | [x] Functional API | — |
| 13 | [x] Deployment (LangGraph Platform) | — |
| 14 | [x] Internals: Pregel, channels | — |

## 03 · LangSmith — `docs/03-langsmith`
_Trace, evaluate, and manage prompts for production reliability._

| # | Doc | Example |
|---|-----|---------|
| 01 | [x] Tracing and observability | [x] `01_tracing.py` |
| 02 | [x] Datasets | [x] `02_dataset.py` |
| 03 | [x] Evaluation and experiments | [x] `03_evaluate.py` |
| 04 | [x] Evaluators (LLM-as-judge) | [x] `04_llm_judge.py` |
| 05 | [x] Prompt management and hub | — |
| 06 | [x] Monitoring dashboards and alerts | — |
| 07 | [x] Annotation queues and feedback | — |
| 08 | [x] Testing in CI/CD | [x] `test_regression.py` |
| 09 | [x] Instrumenting your code (`@traceable`) | — |

## 04 · deepagents — `docs/04-deepagents`
_Build long-horizon agents with planning, sub-agents, and a virtual filesystem._

| # | Doc | Example |
|---|-----|---------|
| 01 | [x] What are deep agents | [x] `01_basic_deep_agent.py` |
| 02 | [x] Planning and todos | — |
| 03 | [x] Subagents and context isolation | [x] `02_subagents.py` |
| 04 | [x] Virtual filesystem | [x] `03_filesystem.py` · [x] `04_checkpointed.py` |
| 05 | [x] Customizing and middleware | — |
| 06 | [x] Implementing a deep agent | — |

## 05 · Expert — `docs/05-expert`
_Apply design patterns, loop/graph engineering, internals, and eval-driven development._

| # | Doc | Example |
|---|-----|---------|
| 01 | [x] The agent loop and loop engineering | [x] `01_bounded_loop.py` |
| 02 | [x] Graph engineering | — |
| 03 | [x] Context engineering | — |
| 04 | [x] Agent design patterns | [x] `02_router_pattern.py` · [x] `03_reflection.py` |
| 05 | [x] Multi-agent system design | — |
| 06 | [x] Production reliability | [x] `04_retry_fallback.py` |
| 07 | [x] Cost and latency optimization | [x] `05_cost_latency.py` |
| 08 | [x] Evaluation-driven development | — |
| 09 | [x] Library internals | — |
| 10 | [x] Idioms and the LangChain way | — |
| 11 | [x] Security and guardrails | — |

## 06 · Production — `docs/06-production`
_Deploy, monitor, and maintain an agentic app as a repeatable pattern._

| # | Doc |
|---|-----|
| 01 | [x] The path to production |
| 02 | [x] Packaging and assistants |
| 03 | [x] Deploying |
| 04 | [x] Monitoring |
| 05 | [x] Maintenance and iteration |
| 06 | [x] The production pattern checklist |

_Example project: `examples/06-production/` (`app/agent.py`, `eval_gate.py`, `langgraph.json`)._
