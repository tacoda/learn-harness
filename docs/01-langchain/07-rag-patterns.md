# 07 · RAG Patterns

## Mental model

Naive RAG — embed the query, fetch top-k, stuff into the prompt — is the *floor*, not the ceiling. Every advanced pattern targets one specific failure of that floor: the query is worded badly, the chunks are too small to answer, the top-k is noisy, or the corpus needs structured filtering. **Diagnose the failure first, then pick the pattern.** And there's a prior architectural choice that shapes everything: is retrieval a **fixed step in a chain** (always runs, once) or a **tool an agent calls** (runs when and as often as the model decides)?

## In depth

### Naive RAG (the baseline)

Retrieve once, generate once — the module-04 chain shape:

```python
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt         # includes: "Answer using only the context below: {context}"
    | model
    | StrOutputParser()
)
chain.invoke("What is our refund window?")
```

Fast, predictable, cheap. It fails when the question doesn't lexically resemble the answer, when one retrieval pass isn't enough, or when top-k drags in noise. The patterns below each fix one of those.

### Multi-query

*Problem: the user's phrasing misses relevant chunks.* Generate several paraphrases of the query, retrieve for each, union the results. Widens recall at the cost of extra embedding calls.

```python
from langchain.retrievers.multi_query import MultiQueryRetriever

retriever = MultiQueryRetriever.from_llm(retriever=base_retriever, llm=model)
```

### Contextual compression / re-ranking

*Problem: top-k is relevant-ish but noisy.* Over-fetch, then **compress or re-rank** to keep only what actually bears on the query before it reaches the model.

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

compressor = LLMChainExtractor.from_llm(model)
retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=base_retriever.with_config(search_kwargs={"k": 20}),
)
```

Re-ranking is the same idea with a cross-encoder scoring `query × chunk` pairs and keeping the top few. Fetch 20, rank, keep 4 — higher precision than asking the vector store for 4 directly, because the ranker sees query and chunk *together* instead of comparing pre-computed vectors.

### Parent-document (small-to-big)

*Problem: small chunks retrieve precisely but lack context to answer.* Index **small** child chunks for search, but return their **larger parent** on a hit — precision of small, context of big.

```python
from langchain.retrievers import ParentDocumentRetriever
from langchain.storage import InMemoryStore

retriever = ParentDocumentRetriever(
    vectorstore=vectorstore,          # holds small child chunks
    docstore=InMemoryStore(),         # holds full parent docs
    child_splitter=RecursiveCharacterTextSplitter(chunk_size=200),
    parent_splitter=RecursiveCharacterTextSplitter(chunk_size=1500),
)
```

### Self-query

*Problem: the query mixes semantics with hard filters* ("refund policies **from 2024**"). A self-query retriever uses the model to split the natural-language query into a semantic part **and** a structured metadata filter, then applies both.

```python
from langchain.retrievers.self_query.base import SelfQueryRetriever
# model parses "2024 policies about refunds" -> search "refunds" WHERE year=2024
```

### RAG as a chain vs. RAG as an agent tool

The architectural fork:

| | Retrieval as a **chain step** | Retrieval as an **agent tool** |
|---|---|---|
| When retrieval runs | Always, exactly once, up front | Only if the model decides to; can repeat/refine |
| Control flow | Fixed, linear, predictable | Dynamic, model-driven |
| Latency & cost | Lower, bounded | Higher, variable |
| Best for | FAQ, single-hop Q&A, known-shape questions | Multi-hop, "search then search again," mixed tasks |

As a tool, retrieval is just a `@tool` wrapping `retriever.invoke`, handed to `create_agent`:

```python
from langchain.tools import tool
from langchain.agents import create_agent

@tool
def search_docs(query: str) -> str:
    """Search the knowledge base for relevant passages."""
    docs = retriever.invoke(query)
    return "\n\n".join(d.page_content for d in docs)

agent = create_agent(model="claude-sonnet-4-6", tools=[search_docs])
```

Now the model can search, read, reformulate, and search again — real multi-hop retrieval — but you pay in latency and unpredictability. The chain form guarantees exactly one retrieval; the agent form trades that guarantee for adaptability. There's also a hybrid: `dynamicSystemPromptMiddleware` can run retrieval **before the model call** and inject the results into the system prompt (module 10), giving chain-like determinism inside an agent.

## Why it matters

Every pattern above is a **precision/recall/latency trade** dressed up as a technique. Multi-query and parent-document buy recall/context with extra calls; compression and re-ranking buy precision with extra compute; self-query buys exactness with a parsing step; agentic RAG buys adaptability with latency and non-determinism. The engineering skill is not knowing the patterns — it's *measuring which failure you actually have* and spending complexity only there. Reaching for agentic multi-hop RAG when naive RAG would answer the question is the RAG equivalent of premature optimization: more moving parts, more cost, more ways to be wrong.

## Pitfalls

- **Adding patterns without measuring.** Stacking multi-query + compression + re-ranking on a problem naive RAG already solved just adds latency and failure modes. Build an eval set first (LangSmith track), then add the *one* pattern that moves the number.
- **Agentic RAG by default.** It's slower, costlier, and non-deterministic. Use a chain unless the task genuinely needs multi-hop or conditional retrieval.
- **Compression/re-ranking on tiny `k`.** These only help when you *over-fetch* first. Compressing 4 chunks down to 3 buys nothing — fetch 20, rank to 4.
- **Ignoring the generation prompt.** Retrieval can be perfect and the answer still wrong if the prompt doesn't instruct the model to ground in the context and refuse when it's absent.
- **Prompt injection via retrieved content.** Retrieved chunks are untrusted data. Instruct the model to treat context as data, not instructions — and never let retrieved text silently override the system prompt.
- **Stale `RetrievalQA` / `ConversationalRetrievalChain`.** Those 0.x convenience chains are legacy. Compose the pipe yourself or use an agent tool — you get transparency and control the black-box chains hid.

## Exercises

1. Build naive RAG, then craft a question whose wording defeats it; fix it with `MultiQueryRetriever` and confirm recall improves.
2. Over-fetch `k=20` and add contextual compression; compare the chunks that reach the model before and after.
3. Implement parent-document retrieval and show that a hit on a small child returns the larger parent.
4. Wrap the same retriever as an agent tool; ask a two-hop question and watch the agent search twice in the trace.
5. Write down, for one real question set, which single pattern you'd add and what metric would justify it.

## Further reading

- Retrieval & RAG: https://docs.langchain.com/oss/python/langchain/retrieval
- Retrievers: https://docs.langchain.com/oss/python/integrations/retrievers
- Agents (retrieval as a tool): https://docs.langchain.com/oss/python/langchain/agents
- Middleware (dynamic prompt RAG): https://docs.langchain.com/oss/python/langchain/middleware
