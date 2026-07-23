"""Router / classifier pattern with cost tiering.

Demonstrates docs/05-expert/04-agent-design-patterns.md (Routing / classifier).

A *cheap* model classifies the incoming query; a conditional edge dispatches it
to a specialized handler backed by a *strong* model. This is a direct cost
lever: the expensive model only runs on the branch that needs it, and each
handler keeps a narrow, task-specific prompt.

Model tiering is a config change, not a rewrite — CHEAP_MODEL routes, MODEL
works. Both default to MODEL when unset.
"""

import os
from typing import Literal, TypedDict

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
CHEAP_MODEL = os.environ.get("CHEAP_MODEL", MODEL)

router_model = init_chat_model(CHEAP_MODEL, model_provider="openai")   # cheap, fast
worker_model = init_chat_model(MODEL, model_provider="openai")         # strong

Route = Literal["billing", "technical", "general"]


class Classification(BaseModel):
    """Structured verdict from the cheap router."""

    category: Route = Field(description="Which specialized handler should take this query")


router = router_model.with_structured_output(Classification)


class RouterState(TypedDict):
    query: str
    route: Route
    answer: str


def classify(state: RouterState) -> dict:
    result = router.invoke(
        [
            {"role": "system", "content": "Classify the support query as billing, technical, or general."},
            {"role": "user", "content": state["query"]},
        ]
    )
    return {"route": result.category}


def pick(state: RouterState) -> Route:
    """Pure dispatch: map the classified route to a handler node name."""
    return state["route"]


def _handler(state: RouterState, persona: str) -> dict:
    resp = worker_model.invoke(
        [
            {"role": "system", "content": f"You are a {persona}. Answer in one sentence."},
            {"role": "user", "content": state["query"]},
        ]
    )
    return {"answer": resp.content.strip()}


def billing_handler(state: RouterState) -> dict:
    return _handler(state, "billing specialist")


def technical_handler(state: RouterState) -> dict:
    return _handler(state, "technical support engineer")


def general_handler(state: RouterState) -> dict:
    return _handler(state, "general support agent")


def build_router_graph():
    g = StateGraph(RouterState)
    g.add_node("classify", classify)
    g.add_node("billing", billing_handler)
    g.add_node("technical", technical_handler)
    g.add_node("general", general_handler)
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        pick,
        {"billing": "billing", "technical": "technical", "general": "general"},
    )
    for node in ("billing", "technical", "general"):
        g.add_edge(node, END)
    return g.compile()


if __name__ == "__main__":
    # Self-check the deterministic dispatch: each label reaches its own branch.
    branches = {"billing": "billing", "technical": "technical", "general": "general"}
    for label in ("billing", "technical", "general"):
        assert pick({"query": "", "route": label, "answer": ""}) == branches[label]

    graph = build_router_graph()

    query = "I was charged twice for my subscription this month and want a refund."
    result = graph.invoke({"query": query, "route": "general", "answer": ""})
    print(f"Query:  {query}")
    print(f"Route:  {result['route']}  (classified by cheap model {CHEAP_MODEL})")
    print(f"Answer: {result['answer']}  (handled by strong model {MODEL})")

    # A clear billing query must route to the billing branch.
    assert result["route"] == "billing", f"expected billing route, got {result['route']}"
    print("\nRouting picked the correct branch.")
