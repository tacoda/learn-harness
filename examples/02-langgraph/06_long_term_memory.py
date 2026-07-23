"""Long-term memory with a Store.

Mirrors docs/02-langgraph/06-memory-short-and-long-term.md.

Where a checkpointer holds per-thread (short-term) state, a Store holds
cross-thread (long-term) memory keyed as namespace -> key -> value. Compile
with store=, and LangGraph injects the store into any node that declares a
`store: BaseStore` parameter. One node writes a memory; a later node reads
it back. No LLM -- the round-trip is pure store logic.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

NAMESPACE = ("user-42", "memories")


class State(TypedDict):
    user_id: str
    recalled: str


def write_memory(state: State, *, store: BaseStore) -> dict:
    # A namespace is a tuple you design to scope data; the value is a
    # JSON-serializable dict.
    store.put(NAMESPACE, "food-pref", {"text": "prefers key lime pie"})
    return {}


def read_memory(state: State, *, store: BaseStore) -> dict:
    item = store.get(NAMESPACE, "food-pref")
    return {"recalled": item.value["text"]}


def build_graph(store: InMemoryStore):
    builder = StateGraph(State)
    builder.add_node("write_memory", write_memory)
    builder.add_node("read_memory", read_memory)
    builder.add_edge(START, "write_memory")
    builder.add_edge("write_memory", "read_memory")
    builder.add_edge("read_memory", END)
    return builder.compile(store=store)


if __name__ == "__main__":
    store = InMemoryStore()
    graph = build_graph(store)

    result = graph.invoke({"user_id": "user-42", "recalled": ""})
    print("Recalled memory:", result["recalled"])

    # Self-check: the value round-tripped through the store, and the store
    # itself holds it under the namespace (cross-thread durability).
    assert result["recalled"] == "prefers key lime pie", result
    assert store.get(NAMESPACE, "food-pref").value == {"text": "prefers key lime pie"}
    print("\nOK: memory written in one node round-tripped to another via the Store.")
