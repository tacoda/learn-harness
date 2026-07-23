"""Minimal StateGraph.

Mirrors docs/02-langgraph/01-why-langgraph-mental-model.md and
docs/02-langgraph/02-stategraph-state-and-reducers.md.

The smallest complete graph: a TypedDict state, one node that returns a
partial update, START -> node -> END wiring, compile, invoke. No LLM.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    topic: str
    draft: str


def write(state: State) -> dict:
    # A node is just State -> dict; it returns a PARTIAL update, not the
    # whole state. The engine merges it in using each key's reducer.
    return {"draft": f"A short note on {state['topic']}."}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("write", write)
    builder.add_edge(START, "write")
    builder.add_edge("write", END)
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    result = graph.invoke({"topic": "reducers", "draft": ""})

    print("Result:", result)
    print("Draft:", result["draft"])

    # Self-check: output has the expected shape and the node's update landed.
    assert set(result.keys()) == {"topic", "draft"}, result
    assert result["topic"] == "reducers"
    assert result["draft"] == "A short note on reducers."
    print("\nOK: node returned a partial update and it merged into state.")
