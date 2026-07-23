"""Mirrors docs/04-deepagents/04-virtual-filesystem.md (persistence within a thread)
and the LangGraph checkpointer story from docs/04-deepagents/06-implementing-a-deep-agent.md.

A deep agent is a compiled LangGraph graph, so persistence works exactly as it
does anywhere in LangGraph: pass a checkpointer and invoke with a `thread_id`.
State (message history) is persisted per thread, so a second turn on the same
thread_id remembers the first.
"""

import os

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")


def build_agent():
    model = init_chat_model(MODEL, model_provider="openai")
    return create_deep_agent(
        model=model,
        system_prompt="You are a friendly assistant with a good memory. Keep answers to one short sentence.",
        checkpointer=InMemorySaver(),
    )


if __name__ == "__main__":
    agent = build_agent()
    config = {"configurable": {"thread_id": "conv-1"}}

    r1 = agent.invoke(
        {"messages": [{"role": "user", "content": "My favorite color is teal. Remember that."}]},
        config=config,
    )
    print("=== Turn 1 ===")
    print(r1["messages"][-1].content)

    r2 = agent.invoke(
        {"messages": [{"role": "user", "content": "What is my favorite color?"}]},
        config=config,
    )
    print("\n=== Turn 2 (same thread_id — should recall) ===")
    print(r2["messages"][-1].content)

    # The second turn's state should contain the full history from both turns,
    # proving the checkpointer persisted state across invocations.
    assert len(r2["messages"]) > len(r1["messages"]), "expected turn 2 to build on turn 1's persisted history"
    print("\nself-check ok: turn 2 state carries turn 1's messages (checkpointer persisted the thread)")
