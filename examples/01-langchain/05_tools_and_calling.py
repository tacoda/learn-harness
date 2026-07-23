"""Tool calling: bind tools, let the model pick one, execute it, feed the result back. Mirrors docs/01-langchain/05-tools-and-tool-calling.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, ToolMessage
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


TOOLS_BY_NAME = {get_weather.name: get_weather, add.name: add}


def run_one_round(question: str) -> str:
    """One manual tool round: model proposes a call, we execute it, the model answers with the result."""
    model_with_tools = model.bind_tools([get_weather, add])
    messages = [HumanMessage(question)]

    ai = model_with_tools.invoke(messages)
    assert ai.tool_calls, "expected the model to request a tool call for this question"
    messages.append(ai)

    for call in ai.tool_calls:
        selected = TOOLS_BY_NAME[call["name"]]
        result = selected.invoke(call["args"])
        # Hand-built ToolMessages must carry the originating call's id to match result to request.
        messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        print(f"tool call -> {call['name']}({call['args']}) = {result}")

    final = model_with_tools.invoke(messages)
    return final.content


if __name__ == "__main__":
    answer = run_one_round("What's the weather in Boston?")
    print("final ->", answer)
