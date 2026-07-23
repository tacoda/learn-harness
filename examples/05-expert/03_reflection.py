"""Evaluator-optimizer (reflection) loop in LangGraph.

Demonstrates docs/05-expert/04-agent-design-patterns.md (Evaluator-optimizer).

A generator node produces (or revises) an answer; a critic node grades it
against explicit criteria and returns structured feedback. A conditional edge
loops back to the generator on a failing verdict and exits on a passing one —
bounded by a max-iterations counter so a stubborn critic can't spin forever.

The loop bound is the non-LLM logic here, and it is asserted.
"""

import os
from typing import TypedDict

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

model = init_chat_model(MODEL, model_provider="openai")

MAX_ITERATIONS = 3


class Critique(BaseModel):
    """Structured verdict from the critic node."""

    passed: bool = Field(description="True if the draft fully meets every criterion")
    feedback: str = Field(description="Specific, actionable improvements if it did not pass")


critic = model.with_structured_output(Critique)

TASK = (
    "Write a single tweet (under 200 characters) announcing a developer tool "
    "called Keystone. It must name the tool, state one concrete benefit, and "
    "end with a call to action."
)


class ReflectState(TypedDict):
    task: str
    draft: str
    feedback: str
    iterations: int
    passed: bool


def generate(state: ReflectState) -> dict:
    if state["draft"]:
        prompt = (
            f"Task:\n{state['task']}\n\nYour previous draft:\n{state['draft']}\n\n"
            f"Critic feedback:\n{state['feedback']}\n\nRewrite an improved draft."
        )
    else:
        prompt = f"Task:\n{state['task']}\n\nWrite the first draft."
    resp = model.invoke([{"role": "user", "content": prompt}])
    return {"draft": resp.content.strip(), "iterations": state["iterations"] + 1}


def evaluate(state: ReflectState) -> dict:
    verdict = critic.invoke(
        [
            {"role": "system", "content": "You are a strict editor grading a draft against the task's criteria."},
            {"role": "user", "content": f"Task:\n{state['task']}\n\nDraft:\n{state['draft']}"},
        ]
    )
    return {"passed": verdict.passed, "feedback": verdict.feedback}


def route(state: ReflectState) -> str:
    """Exit on a pass, or when the iteration budget is exhausted."""
    if state["passed"] or state["iterations"] >= MAX_ITERATIONS:
        return "done"
    return "revise"


def build_reflection_graph():
    g = StateGraph(ReflectState)
    g.add_node("generate", generate)
    g.add_node("evaluate", evaluate)
    g.add_edge(START, "generate")
    g.add_edge("generate", "evaluate")
    g.add_conditional_edges("evaluate", route, {"revise": "generate", "done": END})
    return g.compile()


if __name__ == "__main__":
    graph = build_reflection_graph()
    result = graph.invoke(
        {"task": TASK, "draft": "", "feedback": "", "iterations": 0, "passed": False},
        {"recursion_limit": 50},
    )

    print(f"Iterations run: {result['iterations']} (max {MAX_ITERATIONS})")
    print(f"Critic passed:  {result['passed']}")
    print(f"Final draft:\n  {result['draft']}")

    # The loop must always terminate within the bound.
    assert 1 <= result["iterations"] <= MAX_ITERATIONS, "reflection loop exceeded its bound"
    print("\nLoop terminated within its iteration bound.")
