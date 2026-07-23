"""Bounding an agent/graph loop.

Demonstrates docs/05-expert/01-the-agent-loop-and-loop-engineering.md.

A LangGraph cycle can fail by *not terminating*. Two bounds keep it in check:

  1. A *soft* step-budget guard: a counter in state that a routing edge reads
     and uses to wind the loop down gracefully at a chosen budget.
  2. A *hard* ``recursion_limit``: LangGraph's runtime ceiling that raises
     ``GraphRecursionError`` before an unbounded loop can run away.

Both are shown below; each is asserted.
"""

import operator
import os
from typing import Annotated, TypedDict

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

model = init_chat_model(MODEL, model_provider="openai")

BUDGET = 3          # soft bound: stop the loop after this many work steps
HARD_LIMIT = 5      # hard bound: recursion_limit for the runaway demo


class LoopState(TypedDict):
    count: int
    budget: int
    scratch: Annotated[list[str], operator.add]


def work(state: LoopState) -> dict:
    """One unit of agent work — a real model call, then record the step."""
    n = state["count"] + 1
    resp = model.invoke(
        [{"role": "user", "content": f"Reply with exactly the number {n}, nothing else."}]
    )
    return {"count": n, "scratch": [f"step {n}: {resp.content.strip()}"]}


def should_continue(state: LoopState) -> str:
    """Soft bound: the routing edge winds the loop down at the budget."""
    return "stop" if state["count"] >= state["budget"] else "continue"


def build_bounded_graph():
    g = StateGraph(LoopState)
    g.add_node("work", work)
    g.add_edge(START, "work")
    g.add_conditional_edges("work", should_continue, {"continue": "work", "stop": END})
    return g.compile()


def tick(state: LoopState) -> dict:
    """A cheap no-LLM step used only for the runaway (hard-bound) demo."""
    return {"count": state["count"] + 1, "scratch": [f"tick {state['count'] + 1}"]}


def build_runaway_graph():
    """A loop with no soft guard — it only stops via recursion_limit."""
    g = StateGraph(LoopState)
    g.add_node("tick", tick)
    g.add_edge(START, "tick")
    g.add_conditional_edges("tick", lambda _s: "continue", {"continue": "tick"})
    return g.compile()


if __name__ == "__main__":
    # 1) Soft bound: the step-budget guard stops the loop exactly at BUDGET.
    bounded = build_bounded_graph()
    result = bounded.invoke(
        {"count": 0, "budget": BUDGET, "scratch": []},
        {"recursion_limit": 50},
    )
    print(f"Soft bound: loop ran {result['count']} step(s), budget was {BUDGET}")
    for line in result["scratch"]:
        print(f"  {line}")
    assert result["count"] == BUDGET, "step-budget guard did not stop at the budget"

    # 2) Hard bound: an unbounded loop is stopped by recursion_limit.
    runaway = build_runaway_graph()
    raised = False
    try:
        runaway.invoke({"count": 0, "budget": 0, "scratch": []}, {"recursion_limit": HARD_LIMIT})
    except GraphRecursionError:
        raised = True
    print(f"\nHard bound: recursion_limit={HARD_LIMIT} raised GraphRecursionError: {raised}")
    assert raised, "runaway loop was not stopped by recursion_limit"

    print("\nBoth bounds enforced.")
