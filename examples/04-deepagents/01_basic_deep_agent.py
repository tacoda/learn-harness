"""Mirrors docs/04-deepagents/01-what-are-deep-agents.md.

The minimal deep agent: `create_deep_agent` with one custom tool and a
`system_prompt` (NOT `instructions=` — that is the old 0.x name). The returned
object is a compiled LangGraph graph you invoke with {"messages": [...]}.
"""

import os

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from deepagents import create_deep_agent

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")


@tool
def word_count(text: str) -> int:
    """Return the number of whitespace-separated words in `text`."""
    return len(text.split())


def build_agent():
    model = init_chat_model(MODEL, model_provider="openai")
    return create_deep_agent(
        model=model,
        tools=[word_count],
        system_prompt=(
            "You are a concise writing assistant. When asked how many words are "
            "in a phrase, call the word_count tool and report the number."
        ),
    )


if __name__ == "__main__":
    agent = build_agent()

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "How many words are in 'the quick brown fox'? Answer with just the number."}]}
    )

    final = result["messages"][-1]
    print("=== Final message ===")
    print(final.content)

    # Pure-logic self-check: the tool itself must count correctly.
    assert word_count.invoke({"text": "the quick brown fox"}) == 4
    print("\nself-check ok: word_count('the quick brown fox') == 4")
