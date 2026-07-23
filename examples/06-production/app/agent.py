"""The deployable artifact for docs/06-production/02-packaging-and-assistants.md.

This module exposes a module-level ``graph`` (a compiled LangGraph graph from
``create_agent``). ``langgraph.json`` points at ``./app/agent.py:graph`` — that
single reference is the entire deployment contract. ``langgraph dev`` loads this
object into a local Agent Server; a real deployment loads the same object into a
Postgres-backed one. Nothing about the graph changes between the two.

Note there is deliberately NO checkpointer passed here: the Agent Server supplies
a production checkpointer for you. Hardcoding an ``InMemorySaver`` would silently
lose durability in prod (see docs/06-production/02 Pitfalls).
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain_core.tools import tool

model = init_chat_model(MODEL, model_provider="openai")

# A tiny, deterministic "backend" so the agent has a real tool to call. In a
# production app this would hit your order system; the shape is identical.
_ORDERS = {
    "A1001": "shipped",
    "A1002": "delivered",
    "A1003": "cancelled",
}


@tool
def look_up_order(order_id: str) -> str:
    """Look up the current status of an order by its ID (e.g. 'A1001')."""
    return _ORDERS.get(order_id.strip().upper(), "unknown")


SYSTEM_PROMPT = (
    "You are a support triage agent. When a user asks about an order, call "
    "look_up_order with the order ID and state the status plainly. If the order "
    "is unknown, say you could not find it and escalate. Keep replies short."
)

# create_agent compiles to a LangGraph graph. This compiled object is what the
# manifest deploys — the exact thing you have been building all along.
graph = create_agent(
    model,
    tools=[look_up_order],
    system_prompt=SYSTEM_PROMPT,
)
