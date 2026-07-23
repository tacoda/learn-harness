# 06 · Retrieval, Embeddings & Vector Stores

## Mental model

Retrieval is how you put **your** data in front of a model that was trained without it. The pipeline is always the same four stages: **load** documents → **split** them into chunks → **embed** each chunk into a vector → **store and search** those vectors. The thing you hand to a chain or agent at the end is a **retriever** — and, like everything else, a retriever is a `Runnable` (`retriever.invoke(query) -> list[Document]`). Get the four stages right and RAG (module 07) is just wiring.

## In depth

### 1. Load

Document loaders turn a source (file, URL, database) into `Document` objects — `page_content` plus a `metadata` dict:

```python
from langchain_community.document_loaders import TextLoader, PyPDFLoader

docs = TextLoader("handbook.txt").load()
docs = PyPDFLoader("report.pdf").load()   # one Document per page, with page metadata
```

Loaders live in `langchain_community` (community integrations) — a separate install from core. Metadata set here (source, page, section) is what you'll filter on later, so populate it deliberately.

### 2. Split

Models and embeddings have context limits, and retrieval precision improves when chunks are focused. `RecursiveCharacterTextSplitter` is the sane default — it splits on paragraph/line/word boundaries before falling back to hard cuts:

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
chunks = splitter.split_documents(docs)
```

`chunk_overlap` carries a little context across the boundary so a sentence split down the middle still retrieves. Chunk size is a genuine tradeoff (see *Why it matters*): too big dilutes relevance, too small loses context.

### 3. Embed

An embeddings model maps text to a vector; semantically similar text lands nearby. Same provider-agnostic pattern as chat models:

```python
from langchain_openai import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

embeddings.embed_query("one string -> one vector")
embeddings.embed_documents(["batch", "of", "strings"])
```

The embedding model used to *index* must be the same one used to *query* — different models produce incompatible vector spaces.

### 4. Store & search

A vector store holds the vectors and does nearest-neighbor search. Start in-memory, swap to a real backend (pgvector, Chroma, FAISS, …) without changing the interface:

```python
from langchain_core.vectorstores import InMemoryVectorStore

store = InMemoryVectorStore.from_documents(chunks, embedding=embeddings)

store.similarity_search("How do I reset a password?", k=4)
store.similarity_search("reset password", k=4, filter={"source": "handbook.txt"})
```

`k` caps results; `filter` restricts by metadata *before* ranking — cheap, exact pre-filtering that keeps irrelevant partitions out of the search entirely.

### The retriever interface

Call `.as_retriever()` to get a `Runnable` you can pipe into a chain:

```python
retriever = store.as_retriever(search_kwargs={"k": 4})
retriever.invoke("How do I reset a password?")   # -> list[Document]
```

Because it's a Runnable, it slots straight into the RAG chain shape from module 04 (`{"context": retriever, "question": RunnablePassthrough()} | prompt | model`) or becomes a tool an agent can call.

### Similarity vs. MMR

Plain similarity returns the *k* nearest chunks — which are often near-duplicates of each other. **Maximal Marginal Relevance (MMR)** trades a little relevance for diversity, pulling chunks that are relevant *and* different from each other:

```python
retriever = store.as_retriever(
    search_type="mmr",
    search_kwargs={"k": 4, "fetch_k": 20, "lambda_mult": 0.5},
)
```

`fetch_k` is the candidate pool MMR diversifies from; `lambda_mult` dials relevance (1.0) vs. diversity (0.0). Use MMR when your corpus is repetitive and top-k keeps returning the same paragraph five ways.

### Metadata filtering

Filtering is your precision lever *before* semantic search. Structure metadata at load time (tenant, doc type, date, access level) so you can scope every query:

```python
retriever = store.as_retriever(
    search_kwargs={"k": 4, "filter": {"tenant": "acme", "doc_type": "policy"}},
)
```

For multi-tenant or access-controlled data this is not optional — it's how you keep tenant A's chunks out of tenant B's answers.

## Why it matters

Retrieval quality is set long before the model sees anything — it's decided by **chunking, embedding choice, and search strategy**, and no prompt engineering downstream can recover chunks you failed to retrieve. The central tradeoff is chunk size: large chunks preserve context but dilute the embedding (the vector averages too many topics), small chunks sharpen relevance but fragment meaning across boundaries. The retriever-as-Runnable abstraction is what lets you tune all of this — swap embeddings, swap stores, switch similarity to MMR, add filters — without touching the chain that consumes it. That decoupling is why you can start with `InMemoryVectorStore` and graduate to pgvector by changing one constructor.

## Pitfalls

- **Mismatched index/query embeddings.** Indexing with one model and querying with another silently returns garbage. Pin the embedding model.
- **Default chunk size for every corpus.** Code, prose, and tables want different splitters and sizes. Tune per source; measure retrieval, don't guess.
- **No metadata.** Without it you can't filter, can't cite sources, and can't enforce access. Populate metadata at load time — retrofitting means re-indexing.
- **Top-k near-duplicates.** If answers keep citing the same passage, you want MMR, not a bigger `k`.
- **Treating retrieval as solved once it "works" on demo queries.** Recall on the long tail is the real metric — evaluate it (module 07, and the LangSmith track).
- **Community-package confusion.** Loaders are in `langchain_community`, splitters in `langchain_text_splitters`. Core stays lean; these are separate installs.
- **Re-embedding on every query.** Embed and store *once*; only the query is embedded per request. Rebuilding the index per call is a common accidental cost sink.

## Exercises

1. Load a PDF, split with `RecursiveCharacterTextSplitter`, embed, and `similarity_search` — inspect the returned `Document` metadata.
2. Index a repetitive corpus; compare top-4 results from `similarity` vs. `mmr` and describe the difference.
3. Add `tenant` metadata to two document sets in one store and prove a filtered query never returns the wrong tenant's chunks.
4. Sweep `chunk_size` across three values on one document and eyeball which retrieves the most relevant chunk for a fixed query.

## Further reading

- Retrieval overview: https://docs.langchain.com/oss/python/langchain/retrieval
- Embeddings: https://docs.langchain.com/oss/python/integrations/text_embedding
- Vector stores: https://docs.langchain.com/oss/python/integrations/vectorstores
- Text splitters: https://docs.langchain.com/oss/python/langchain/retrieval
