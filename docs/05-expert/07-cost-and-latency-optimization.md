# 07 · Cost & Latency Optimization

## Mental model

Three quantities are in tension and you cannot maximize all three: **cost, latency, and quality.** Every optimization is a trade among them, and the expert skill is knowing which corner of the triangle a given task actually needs. A batch enrichment job wants cheap and can tolerate slow. An interactive chat wants fast and can tolerate expensive. A legal-review agent wants quality and will pay for it in both. There is no "make it good" — there is "make it good *at what this task values*."

The second principle: **you cannot optimize what you don't measure.** Token counts, per-step latency, and cost live in your LangSmith traces (`docs/03-langsmith/01-tracing-and-observability.md`). Optimize against measured traces of real inputs, not intuition — the step you *think* is slow and the step that *is* slow are frequently different.

The dominant cost and latency driver in agentic systems is almost always **tokens through the model, multiplied by the number of model calls.** Nearly every lever below reduces one or both: fewer tokens per call (context engineering), fewer calls per task (loop bounding, routing), cheaper tokens (model tiering, caching), or better-hidden latency (streaming, parallelism).

## In depth

### Model selection and tiering

The highest-leverage decision. You do not need your strongest model for every call. Tier deliberately:

- **Cheap router / classifier** decides what kind of task this is, then dispatches to the right worker (`04-agent-design-patterns.md`, routing).
- **Strong worker** does the reasoning that actually needs capability.
- **Cheap utility model** does the mechanical work around the edges — summarization, tool selection, extraction, evaluation.

```python
router  = init_chat_model("anthropic:claude-haiku-4-5")   # cheap, fast
worker  = init_chat_model("anthropic:claude-sonnet-4-6")  # strong
```

Because everything is provider-agnostic via `init_chat_model` (`docs/00-foundations/03-the-langchain-ecosystem.md`), tiering is a config change, not a rewrite. A single well-placed cheap model — as the summarizer in `SummarizationMiddleware`, as the picker in `LLMToolSelectorMiddleware`, as an evaluator-optimizer's grader — can cut cost substantially with no quality loss on the main path.

### Prompt caching

Providers cache token prefixes so repeated processing of the same tokens (a long stable system prompt, a fixed tool list, a large document) is cheaper and faster on subsequent calls. LangChain exposes three levels:

- **Implicit** — some providers cache automatically and pass on savings, no config (e.g. OpenAI, Gemini).
- **Provider-explicit** — you mark cache points for guaranteed savings: Anthropic's content-block `cache_control`, OpenAI's `prompt_cache_key`, Gemini/Bedrock equivalents.
- **Structural** — order your prompt so the *stable* parts (system prompt, tools, few-shot examples) come first and the *variable* parts (the user's turn) come last, maximizing the cacheable prefix.

Caching is enormously effective for agents specifically, because the agent loop re-sends a growing-but-stable prefix on every one of its many turns. Cache the prefix once and every subsequent loop turn is cheaper. See `docs/01-langchain/01-chat-models-and-messages.md` and the models docs.

### Limiting tool-call rounds

Each loop turn is a model call. Fewer turns = less cost and less latency, linearly. Levers:

- **Bound the loop** (`recursion_limit`, `RemainingSteps`) so it can't run long (`01-the-agent-loop-and-loop-engineering.md`).
- **Better tools.** One well-designed tool that returns exactly what's needed beats three round-trips of narrow tools. Tool design is latency design.
- **Constrain agency.** If a workflow pattern fits, it takes a fixed, small number of calls where an open ReAct loop might take many (`04-agent-design-patterns.md`).

### Parallel tool calls

When the model requests several independent tool calls in one turn, execute them concurrently rather than serially — the loop waits for the slowest, not the sum. LangGraph's tool node parallelizes independent calls; ensure your tools are safe to run concurrently (no shared mutable state). Fan-out via the `Send` API (`02-graph-engineering.md`) is the same idea at the graph level.

### Streaming for perceived latency

Streaming doesn't make the work faster — it makes the *wait* feel shorter by emitting tokens as they're produced. For any interactive surface this is the cheapest, highest-impact latency win because it attacks perceived latency directly: time-to-first-token instead of time-to-completion. Stream model output, and stream intermediate progress (which tool is running) so the user sees the agent working. See `docs/01-langchain/11-streaming.md` and `docs/02-langgraph/08-streaming.md`.

### Truncating and compressing context

Every token in the window is paid for on *every* subsequent turn of the loop. Context engineering (`03-context-engineering.md`) is therefore also cost engineering: trim/summarize history, truncate tool outputs at the source, select tools and retrieved documents narrowly. A single verbose tool result that isn't truncated is re-billed on every following turn until it's summarized away.

### Batching, and caching retrieval/embeddings

- **Batching.** For offline/bulk work, `.batch()` over many inputs amortizes overhead and lets the provider optimize throughput. Not for interactive paths.
- **Cache embeddings.** Embedding the same text repeatedly is pure waste — cache embeddings by content hash. Retrieval corpora are embedded once, not per query.
- **Cache retrieval results.** Identical queries should hit a cache, not re-run the vector search and re-inject the same documents.

### Measuring in LangSmith

LangSmith records token usage, cost, and latency per run and per step. Use it to: find the most expensive step (often an untruncated tool result or an over-strong model on a trivial call), find the latency long-pole (often a slow tool or a serial chain that could parallelize), and *verify* that an optimization actually helped rather than moving the cost elsewhere. Optimize → measure → confirm, on real traces.

### Decision heuristics

- **Interactive UX?** Stream first (perceived latency), then tier the model, then cache the prefix.
- **High volume / batch?** Cheapest model that passes evals, batch the calls, cache embeddings and retrieval.
- **Quality-critical?** Strong model on the reasoning path, but still tier the *utility* calls (summarize/select/grade) to cheap models.
- **Agent taking too long?** Count the tool rounds in a trace first. Reduce rounds (better tools, bound the loop) before anything else.
- **Bill too high?** Find the top-cost step in LangSmith. It's usually context bloat (fix: truncate/summarize) or an over-strong model on a cheap task (fix: tier).

## Why it matters

Cost and latency are not afterthoughts you tune before launch — they're determined by architecture decisions (which model, how many calls, how much context) made throughout the build. A team that ships without measuring discovers at scale that a single untruncated tool or an always-strong model quietly multiplied their bill and their p95 latency. Treating cost/latency as a first-class, measured dimension from day one — the same way you treat correctness — is what keeps an agent economically viable in production.

## Pitfalls

- **One strong model for everything.** The most common overspend. Tier: cheap for routing/utility, strong for reasoning.
- **Optimizing by intuition.** The slow/expensive step is rarely the one you'd guess. Measure in LangSmith first.
- **Ignoring prompt caching in a loop.** The agent re-sends a stable prefix every turn; not caching it re-bills the whole prefix each loop iteration.
- **Serial independent tool calls.** Independent calls run concurrently for free; running them in series pays the sum instead of the max.
- **Untruncated context.** A verbose tool result is re-billed on every subsequent turn. Truncate at the source.
- **Streaming treated as optional for interactive UX.** It's the cheapest perceived-latency win there is.

## Exercises

1. Instrument an agent in LangSmith over 20 real inputs. Identify the single most expensive step and the single slowest step. Are they the same? Fix whichever is worse and confirm the delta in a re-run.
2. Introduce model tiering: route trivial queries to a cheap model and only escalate hard ones. Measure cost and quality (via evals) before and after.
3. Enable explicit prompt caching on a stable system-prompt-plus-tools prefix and measure the token/cost change across a multi-turn loop.
4. Take an agent that issues multiple independent tool calls per turn and confirm they execute in parallel. Measure the latency difference vs. forcing them serial.

## Further reading

- Models (prompt caching, batch): https://docs.langchain.com/oss/python/langchain/models
- Context engineering (context = cost): https://docs.langchain.com/oss/python/langchain/context-engineering
- Streaming: https://docs.langchain.com/oss/python/langchain/streaming
- LangSmith tracing (measuring cost/latency): `docs/03-langsmith/01-tracing-and-observability.md`, `06-monitoring-dashboards-alerts.md`
