"""Streaming: token streaming and step updates from a create_agent agent. Mirrors docs/01-langchain/11-streaming.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessageChunk
from langchain.tools import tool

model = init_chat_model(MODEL, model_provider="openai")


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's always sunny in {city}!"


agent = create_agent(model=model, tools=[get_weather])

INPUTS = {"messages": [{"role": "user", "content": "What's the weather in Boston? Explain briefly."}]}


def stream_updates() -> None:
    """stream_mode='updates' emits one state delta per completed node (model / tools)."""
    print("--- updates (step-by-step) ---")
    for chunk in agent.stream(INPUTS, stream_mode="updates", version="v2"):
        if chunk["type"] == "updates":
            for source, update in chunk["data"].items():
                if source in ("model", "tools"):
                    last = update["messages"][-1]
                    print(f"step: {source} -> {getattr(last, 'content', last)!r}")


def stream_tokens() -> None:
    """stream_mode='messages' streams model tokens as they are generated."""
    print("--- messages (token stream) ---")
    for chunk in agent.stream(INPUTS, stream_mode="messages", version="v2"):
        if chunk["type"] == "messages":
            token, metadata = chunk["data"]
            if isinstance(token, AIMessageChunk) and token.text:
                print(token.text, end="", flush=True)
    print()


if __name__ == "__main__":
    stream_updates()
    stream_tokens()
