"""Human-in-the-loop with interrupt().

Mirrors docs/02-langgraph/07-human-in-the-loop-interrupts.md.

`interrupt(payload)` pauses the graph mid-node and surfaces the payload to
the caller. A second invoke with Command(resume=value) re-enters the node;
the interrupt() call now RETURNS that value and the node runs to completion.
Two invokes, one logical run, tied together by thread_id. HITL always needs
a checkpointer. No LLM.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command


class State(TypedDict):
    recipient: str
    status: str


def approval_node(state: State) -> dict:
    decision = interrupt({"action": "send_email", "to": state["recipient"]})
    # Anything below only runs AFTER a resume; put side effects here (the
    # node re-runs on resume, so pre-interrupt effects would happen twice).
    if decision == "approve":
        return {"status": "sent"}
    return {"status": "cancelled"}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("approval", approval_node)
    builder.add_edge(START, "approval")
    builder.add_edge("approval", END)
    return builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    graph = build_graph()
    config = {"configurable": {"thread_id": "1"}}

    # First call runs until interrupt(), then stops.
    paused = graph.invoke({"recipient": "ian@example.com", "status": ""}, config)
    print("Paused. Interrupt payload:", paused["__interrupt__"])

    # A human approves; resume with Command(resume=...).
    final = graph.invoke(Command(resume="approve"), config)
    print("Resumed. Final status:", final["status"])

    # Self-check: the run paused (surfaced __interrupt__) then resumed to
    # completion with the approved outcome.
    assert "__interrupt__" in paused, paused
    assert final["status"] == "sent", final
    print("\nOK: graph interrupted for approval, then resumed to 'sent'.")
