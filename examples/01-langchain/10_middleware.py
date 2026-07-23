"""Middleware: a custom @before_model hook plus a built-in, running inside the agent loop. Mirrors docs/01-langchain/10-middleware.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentState, SummarizationMiddleware, before_model
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langgraph.runtime import Runtime

model = init_chat_model(MODEL, model_provider="openai")

# Module-level flag so the self-check can prove the hook actually fired.
CALLS = {"before_model": 0}


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's always sunny in {city}!"


@before_model
def log_before_model(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Fires before each model call. Returning None is pass-through (changes nothing)."""
    CALLS["before_model"] += 1
    print(f"[before_model] call #{CALLS['before_model']} with {len(state['messages'])} messages")
    return None


agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a concise weather assistant.",
    middleware=[
        # Custom hook (runs first on the way in) ...
        log_before_model,
        # ... plus a built-in that compacts history once it grows past the trigger.
        SummarizationMiddleware(model=model, trigger={"tokens": 4000}),
    ],
)


if __name__ == "__main__":
    result = agent.invoke({"messages": [{"role": "user", "content": "Weather in San Francisco?"}]})
    # The loop calls the model at least once (initial) and again after the tool result.
    assert CALLS["before_model"] >= 1, "before_model middleware should have fired at least once"
    print("before_model fired ->", CALLS["before_model"], "time(s)")
    print("final ->", result["messages"][-1].content)
