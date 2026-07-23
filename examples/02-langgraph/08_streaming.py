"""Streaming: updates, values, and token-level messages.

Mirrors docs/02-langgraph/08-streaming.md.

A graph run is a sequence, and stream_mode picks the lens:
  - "updates" -- only the delta each node returned, keyed by node name
  - "values"  -- the full state after each super-step
  - "messages" -- LLM tokens as they generate, for streaming to a UI
Requires OPENAI_API_KEY.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import Annotated, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

model = init_chat_model(MODEL, model_provider="openai")


class State(TypedDict):
    messages: Annotated[list, add_messages]


def call_model(state: State) -> dict:
    return {"messages": [model.invoke(state["messages"])]}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("model", call_model)
    builder.add_edge(START, "model")
    builder.add_edge("model", END)
    return builder.compile()


if __name__ == "__main__":
    graph = build_graph()
    prompt = {"messages": [{"role": "user", "content": "Name three primary colors."}]}

    print("=== stream_mode='updates' (per-node deltas) ===")
    for chunk in graph.stream(prompt, stream_mode="updates"):
        print(chunk)

    print("\n=== stream_mode='values' (full state per super-step) ===")
    for chunk in graph.stream(prompt, stream_mode="values"):
        print("state messages:", len(chunk["messages"]))

    print("\n=== stream_mode='messages' (token streaming) ===")
    for token, metadata in graph.stream(prompt, stream_mode="messages"):
        # Each event is (message_chunk, metadata); print the token text.
        if token.content:
            print(token.content, end="", flush=True)
    print("\n\nDone.")
