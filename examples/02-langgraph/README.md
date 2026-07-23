# 02-langgraph

Runnable examples mirroring `docs/02-langgraph/`. Each script is self-contained,
uses only current LangGraph 1.x / LangChain 1.x v1 APIs (no `AgentExecutor`), and
carries a small `assert`-based self-check wherever there's non-trivial non-LLM logic.

## Coverage

- **StateGraph basics** — TypedDict state, nodes as `State -> dict` partial updates, `START`/`END`, `compile`, `invoke`.
- **Reducers** — the built-in `add_messages` plus a custom dict-merge reducer.
- **Control flow** — conditional edges and a terminating loop.
- **Prebuilt ReAct agent** — `create_react_agent` with a `@tool`.
- **Persistence** — `InMemorySaver` and multi-turn memory keyed by `thread_id`.
- **Long-term memory** — `InMemoryStore` write/read across nodes.
- **Human-in-the-loop** — `interrupt()` and `Command(resume=...)`.
- **Streaming** — `updates`, `values`, and token-level `messages`.
- **Subgraphs** — a compiled graph composed as a node in a parent.
- **Multi-agent** — `create_supervisor` over two `create_react_agent` workers.

## Setup

One `.env` at the repo root serves every track (see `examples/README.md`). Set
`OPENAI_API_KEY` for the scripts that call a model.

```bash
cd examples/02-langgraph
uv sync                                  # create .venv, install locked deps
uv run python 01_hello_stategraph.py
```

`uv run` auto-syncs, so after the first `uv sync` you can just
`uv run python <script>.py`.

## Scripts

| Script | Demonstrates | Doc |
| --- | --- | --- |
| `01_hello_stategraph.py` | Minimal StateGraph: state, one node, compile, invoke | `01-why-langgraph-mental-model.md`, `02-stategraph-state-and-reducers.md` |
| `02_state_reducers.py` | `add_messages` + a custom reducer merging updates | `02-stategraph-state-and-reducers.md` |
| `03_conditional_edges.py` | Conditional edges routing a terminating loop | `03-nodes-edges-control-flow.md` |
| `04_react_agent.py` | `create_react_agent` with a `@tool` | `04-prebuilt-react-agent.md` |
| `05_persistence.py` | `InMemorySaver`, multi-turn memory by `thread_id` | `05-persistence-checkpointers.md` |
| `06_long_term_memory.py` | `InMemoryStore` write/read across nodes | `06-memory-short-and-long-term.md` |
| `07_hitl_interrupt.py` | `interrupt()` + `Command(resume=...)` | `07-human-in-the-loop-interrupts.md` |
| `08_streaming.py` | `stream_mode` `updates` / `values` / `messages` | `08-streaming.md` |
| `09_subgraph.py` | Compiled subgraph as a node in a parent graph | `09-subgraphs.md` |
| `10_multiagent_supervisor.py` | `create_supervisor` over two ReAct workers | `10-multi-agent-architectures.md` |

## Which scripts call a model?

`01`, `02`, `03`, `06`, `07`, and `09` are pure graph mechanics and run with no API
key. `04`, `05`, `08`, and `10` call OpenAI and need `OPENAI_API_KEY`.
