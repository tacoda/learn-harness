"""Prebuilt ReAct agent.

Mirrors docs/02-langgraph/04-prebuilt-react-agent.md.

`create_react_agent` (from langgraph.prebuilt) wires the whole ReAct loop
for you: a model node, a ToolNode that runs tool calls, and a conditional
edge that loops back while there are tool calls and routes to END when
there aren't. This is v1 -- no AgentExecutor. Requires OPENAI_API_KEY.
"""

import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

model = init_chat_model(MODEL, model_provider="openai")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's sunny in {city}."


if __name__ == "__main__":
    agent = create_react_agent(model=model, tools=[get_weather])

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "What's the weather in Austin?"}]}
    )

    for m in result["messages"]:
        m.pretty_print()

    print("\nFinal answer:", result["messages"][-1].content)
