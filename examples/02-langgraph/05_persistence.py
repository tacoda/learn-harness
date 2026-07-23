"""Persistence with a checkpointer.

Mirrors docs/02-langgraph/05-persistence-checkpointers.md.

Compile with InMemorySaver and every super-step boundary is persisted
against a thread_id. Two invokes on the SAME thread_id form one continuous
conversation -- the second call sees the first. The thread_id is the handle
to durable state. Requires OPENAI_API_KEY.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import Annotated, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

model = init_chat_model(MODEL, model_provider="openai")


class State(TypedDict):
    messages: Annotated[list, add_messages]


def call_model(state: State) -> dict:
    return {"messages": [model.invoke(state["messages"])]}


if __name__ == "__main__":
    builder = StateGraph(State)
    builder.add_node("model", call_model)
    builder.add_edge(START, "model")
    builder.add_edge("model", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "user-42"}}

    turn1 = graph.invoke(
        {"messages": [{"role": "user", "content": "My name is Ian. Remember it."}]},
        config,
    )
    print("Turn 1:", turn1["messages"][-1].content)

    turn2 = graph.invoke(
        {"messages": [{"role": "user", "content": "What's my name?"}]},
        config,
    )
    print("Turn 2:", turn2["messages"][-1].content)

    # The second turn's state includes turn 1's messages because both
    # invokes shared thread_id "user-42".
    print(f"\nThread now holds {len(turn2['messages'])} messages "
          "(both turns), so the model can recall the name.")
