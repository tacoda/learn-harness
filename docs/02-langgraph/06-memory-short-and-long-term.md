# 06 · Memory: Short-term & Long-term

## Mental model

Agents need two kinds of memory, and LangGraph gives them two different homes:

- **Short-term memory** is the state of the *current thread* — the conversation so far, scratch variables, intermediate results. It lives in the graph state and is persisted by the **checkpointer** (chapter 5), scoped to a `thread_id`. When the conversation ends, or you switch threads, it's gone from view.
- **Long-term memory** is knowledge that must outlive any single thread — user preferences, learned facts, profiles. It lives in a **`Store`**, a namespaced key-value store that is *cross-thread*. Any thread, any run, can read and write it.

The distinction is about lifetime and scope, not importance. Short-term = "what happened in this conversation." Long-term = "what I know about this user across all conversations." A checkpointer keys on `thread_id`; a store keys on a `namespace` you choose. They're complementary: a node can read long-term facts from the store, use them this turn (short-term), and write new facts back for next time.

## In depth

### Short-term: it's just thread state

You already have short-term memory the moment you attach a checkpointer and use a `thread_id` — the `messages` channel (with `add_messages`) accumulates the conversation, and every super-step persists it. The engineering work in short-term memory is *managing size*: trimming or summarizing old messages so the model's context stays small and cheap. That's context engineering, and it's typically done with a node that rewrites the `messages` channel (or, with `create_agent`, a summarization middleware).

### Long-term: the `Store`

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
graph = builder.compile(checkpointer=checkpointer, store=store)
```

Compile with both `checkpointer=` (short-term) and `store=` (long-term). The store is then injected into your nodes. `InMemoryStore` is the dev implementation; production deployments use a persistent store (e.g. the Postgres-backed store), same interface.

### Namespaces and keys

The store is organized as `namespace -> key -> value`. A namespace is a tuple you design to scope data — commonly `(user_id, "memories")`. A value is a JSON-serializable dict.

```python
namespace = ("user-42", "memories")
store.put(namespace, "food-pref", {"text": "prefers key lime pie"})
item = store.get(namespace, "food-pref")   # -> Item with .value == {"text": ...}
items = store.search(namespace)            # list all items in the namespace
```

Namespacing by user id is what makes the store cross-thread but not cross-user: two conversations with the same user share the namespace; two different users never see each other's memories.

### Reading and writing memories from a node

A node accesses the store through the runtime that LangGraph passes it. In v1 nodes can take a `runtime` argument exposing `runtime.store`:

```python
from langgraph.runtime import Runtime


def remember(state: State, runtime: Runtime) -> dict:
    store = runtime.store
    ns = (state["user_id"], "memories")
    # Read what we know so far.
    known = store.search(ns)
    # Write a new memory derived from this turn.
    store.put(ns, "latest", {"text": state["messages"][-1].content})
    return {"context": [i.value["text"] for i in known]}
```

The pattern is always the same: read relevant memories at the start of a turn to enrich context, write new ones at the end so the next turn (or next thread) benefits. The store call is a side effect; the node still returns a normal partial state update.

### Semantic search over memories

Listing a namespace works when it's small. When memories grow, you want to retrieve by *relevance*, not enumerate everything. Configure the store with an embedding index and `search` accepts a natural-language query:

```python
from langchain.embeddings import init_embeddings
from langgraph.store.memory import InMemoryStore

store = InMemoryStore(
    index={
        "embed": init_embeddings("openai:text-embedding-3-small"),
        "dims": 1536,
    }
)
store.put(("user-42", "memories"), "1", {"text": "lives near Austin, Texas"})
store.put(("user-42", "memories"), "2", {"text": "plays guitar"})

hits = store.search(("user-42", "memories"), query="where does the user live?", limit=3)
# hits ranked by semantic similarity; the Texas memory ranks first.
```

Now retrieval scales: a node embeds the query, the store returns the top-k most relevant memories, and only those enter the model's context. This is retrieval-augmented memory, and it's the difference between "remembers a handful of facts" and "remembers a user's entire history usefully."

## Why it matters

Short-term memory makes a single conversation coherent; long-term memory makes an assistant feel like it *knows you* across sessions. Getting the split right is a design decision with real consequences: put everything in thread state and each new conversation starts amnesiac; put everything in the store and you lose the natural per-conversation scoping and pay to embed transient chatter. The expert move is to keep the thread state small (short-term, aggressively trimmed) and promote only durable facts to the store (long-term, semantically searchable). Because both hang off the same compile call, you can add long-term memory to an existing graph without touching its control flow.

## Pitfalls

- **Confusing the two.** State (checkpointer, `thread_id`) is short-term; `Store` (namespace) is long-term. Trying to get cross-conversation memory from thread state won't work — different threads have different `thread_id`s.
- **Compiling with a store but never passing it to nodes.** Read it via the `runtime` argument (`runtime.store`); a node that ignores the runtime never sees the store.
- **Un-namespaced or over-broad namespaces.** A global namespace leaks one user's memories into another's context. Scope by user (or tenant) id.
- **Semantic search without an index.** `search(query=...)` only ranks semantically if the store was created with an `index=` config; otherwise you get unranked results.
- **Letting short-term memory grow unbounded.** Appending forever to `messages` eventually blows the context window and the budget. Trim or summarize.
- **Stale-tutorial trap.** Pre-1.0 tutorials use `ConversationBufferMemory` and other LangChain memory classes. In v1 those are replaced by checkpointers (short-term) and `Store` (long-term). If a tutorial imports a `*Memory` class from `langchain`, it's the old model.

## Exercises

1. Compile a graph with both a checkpointer and an `InMemoryStore`. In a node, write a fact to `(user_id, "memories")` on turn one; on turn two (same user, *new* thread_id), read it back and confirm it survived the thread switch.
2. Add an embedding index to the store, insert five memories, and `search` with a query that matches only one. Confirm ranking puts the right memory first.
3. Write a node that trims `messages` to the last N before calling the model. Observe the effect on what the model sees.
4. Explain, in two sentences, which of a user's data belongs in thread state vs. the store for a customer-support agent.

## Further reading

- Memory concepts (short vs. long-term): https://docs.langchain.com/oss/python/langgraph/memory
- Persistence & the Store: https://docs.langchain.com/oss/python/langgraph/persistence#memory-store
- Semantic search in the store: https://docs.langchain.com/oss/python/langgraph/persistence#semantic-search
- Managing conversation history: https://docs.langchain.com/oss/python/langgraph/memory#manage-short-term-memory
