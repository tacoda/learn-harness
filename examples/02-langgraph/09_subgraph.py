"""Subgraphs: compose a compiled graph as a node.

Mirrors docs/02-langgraph/09-subgraphs.md.

A subgraph is a compiled graph used as a node inside another graph. When
parent and subgraph SHARE state keys, you hand the compiled subgraph
straight to add_node -- updates flow through transparently. From the
parent's perspective the subgraph runs as one step. No LLM.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    value: int
    log: Annotated[list, lambda a, b: a + b]


def double(state: State) -> dict:
    return {"value": state["value"] * 2, "log": ["subgraph: doubled"]}


def build_subgraph():
    sub = StateGraph(State)
    sub.add_node("double", double)
    sub.add_edge(START, "double")
    sub.add_edge("double", END)
    return sub.compile()


def add_ten(state: State) -> dict:
    return {"value": state["value"] + 10, "log": ["parent: +10"]}


def build_parent():
    subgraph = build_subgraph()
    parent = StateGraph(State)
    parent.add_node("sub", subgraph)  # the whole subgraph is one node
    parent.add_node("add_ten", add_ten)
    parent.add_edge(START, "sub")
    parent.add_edge("sub", "add_ten")
    parent.add_edge("add_ten", END)
    return parent.compile()


if __name__ == "__main__":
    graph = build_parent()
    result = graph.invoke({"value": 3, "log": []})

    print("final value:", result["value"])
    print("log:", result["log"])

    # Self-check: 3 -> (subgraph doubles) 6 -> (parent +10) 16, and the
    # parent sees the subgraph's log entry because the schema is shared.
    assert result["value"] == 16, result["value"]
    assert "subgraph: doubled" in result["log"], result["log"]
    assert result["log"] == ["subgraph: doubled", "parent: +10"], result["log"]
    print("\nOK: parent sees the subgraph's output through the shared schema.")
