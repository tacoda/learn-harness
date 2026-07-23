"""Agents: create_agent runs the model->tools->model loop for you. Mirrors docs/01-langchain/09-agents-create-agent.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import ToolMessage
from langchain.tools import tool

model = init_chat_model(MODEL, model_provider="openai")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's always sunny in {city}!"


@tool
def add(a: int, b: int) -> int:
    """Add two integers together."""
    return a + b


agent = create_agent(
    model=model,
    tools=[get_weather, add],
    system_prompt="You are a concise assistant. Use tools when they help.",
)


if __name__ == "__main__":
    # Input is always {"messages": [...]}; output is the full state.
    result = agent.invoke({"messages": [{"role": "user", "content": "What's the weather in San Francisco?"}]})
    messages = result["messages"]

    # The agent ran the loop itself; confirm a tool was actually invoked.
    tool_calls = [m for m in messages if isinstance(m, ToolMessage)]
    assert tool_calls, "the agent should have called at least one tool for this question"

    print("tool messages ->", len(tool_calls))
    print("final ->", messages[-1].content)
