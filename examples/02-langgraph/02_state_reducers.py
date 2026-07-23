"""State reducers: add_messages plus a custom reducer.

Mirrors docs/02-langgraph/02-stategraph-state-and-reducers.md.

A reducer decides how a node's partial update MERGES into the channel
instead of overwriting it. Here `messages` uses the built-in add_messages
(append / replace-by-id) and `scratch` uses a custom dict-merge reducer.
Two nodes each contribute, and we assert the merges are correct. No LLM.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


def merge_dicts(left: dict, right: dict) -> dict:
    """Custom reducer: merge two dicts instead of clobbering.

    Reducers must be pure; in a parallel super-step you cannot rely on
    which update arrives first, so keep the result order-independent.
    """
    return {**left, **right}


class State(TypedDict):
    messages: Annotated[list, add_messages]
    scratch: Annotated[dict, merge_dicts]


def first(state: State) -> dict:
    return {
        "messages": [{"role": "user", "content": "hello"}],
        "scratch": {"a": 1},
    }


def second(state: State) -> dict:
    return {
        "messages": [{"role": "assistant", "content": "hi"}],
        "scratch": {"b": 2},
    }


def build_graph():
    builder = StateGraph(State)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    result = graph.invoke({"messages": [], "scratch": {}})

    print("messages count:", len(result["messages"]))
    for m in result["messages"]:
        print(f"  {m.type}: {m.content}")
    print("scratch:", result["scratch"])

    # Self-check: add_messages appended both messages (no clobber),
    # and the custom reducer merged both dict fragments.
    assert len(result["messages"]) == 2, result["messages"]
    assert result["messages"][0].content == "hello"
    assert result["messages"][1].content == "hi"
    assert result["scratch"] == {"a": 1, "b": 2}, result["scratch"]
    print("\nOK: add_messages appended and the custom reducer merged both keys.")
