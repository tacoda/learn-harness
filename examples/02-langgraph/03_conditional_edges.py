"""Conditional edges and a terminating loop.

Mirrors docs/02-langgraph/03-nodes-edges-control-flow.md.

A conditional edge attaches a router function to a node: after the node
runs, the router reads state and returns the next destination (a node name
or END). A loop is just an edge that points backward; the router
terminates it once a counter hits its bound. No LLM.
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


def step(state: State) -> dict:
    nxt = state["value"] + 1
    return {"value": nxt, "log": [nxt]}


def keep_going(state: State) -> str:
    # Router returns a node name to loop, or END to stop.
    return "step" if state["value"] < 5 else END


def build_graph():
    builder = StateGraph(State)
    builder.add_node("step", step)
    builder.add_edge(START, "step")
    builder.add_conditional_edges("step", keep_going)  # loops back or exits
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    result = graph.invoke({"value": 0, "log": []})

    print("final value:", result["value"])
    print("log:", result["log"])

    # Self-check: the loop ran exactly until value == 5 and then stopped.
    assert result["value"] == 5, result["value"]
    assert result["log"] == [1, 2, 3, 4, 5], result["log"]
    print("\nOK: conditional edge looped until the counter hit 5, then routed to END.")
