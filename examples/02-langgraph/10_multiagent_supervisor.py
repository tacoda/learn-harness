"""Multi-agent supervisor.

Mirrors docs/02-langgraph/10-multi-agent-architectures.md.

`create_supervisor` (from langgraph_supervisor) builds a hub-and-spoke: you
define specialist workers and it generates the coordinator plus the handoff
tools. The supervisor reads the conversation, calls an auto-generated
handoff tool (e.g. transfer_to_math_expert), the worker runs, and control
returns to the supervisor. Each worker needs a unique name. It returns a
StateGraph you .compile(). Requires OPENAI_API_KEY.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

model = init_chat_model(MODEL, model_provider="openai")


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool
def web_search(query: str) -> str:
    """Look up a fact on the web (stubbed)."""
    return f"Top result for '{query}': LangGraph is a low-level agent framework."


if __name__ == "__main__":
    math_agent = create_react_agent(model=model, tools=[add], name="math_expert")
    research_agent = create_react_agent(
        model=model, tools=[web_search], name="research_expert"
    )

    workflow = create_supervisor(
        agents=[research_agent, math_agent],
        model=model,
        prompt=(
            "You are a supervisor managing a research expert and a math expert. "
            "Delegate research questions to research_expert and arithmetic to "
            "math_expert. Do not answer directly."
        ),
    )
    app = workflow.compile()

    result = app.invoke(
        {"messages": [{"role": "user", "content": "What is 5 + 3?"}]}
    )

    print("=== which worker answered (via handoff tool calls) ===")
    answering_worker = None
    for m in result["messages"]:
        name = getattr(m, "name", None)
        for call in getattr(m, "tool_calls", None) or []:
            print("handoff:", call["name"])
            if call["name"].startswith("transfer_to_"):
                answering_worker = call["name"].removeprefix("transfer_to_")

    print("\nRouted to worker:", answering_worker)
    print("Final answer:", result["messages"][-1].content)
