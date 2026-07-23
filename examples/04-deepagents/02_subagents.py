"""Mirrors docs/04-deepagents/03-subagents-and-context-isolation.md.

A custom sub-agent is declared as a dict with `name`, `description`, and
`system_prompt` (plus optional `tools`/`model`). The main agent gets a `task`
tool from SubAgentMiddleware and delegates focused work to the sub-agent, whose
verbose intermediate work stays quarantined in ITS own context window — only its
final summary flows back up to the parent.
"""

import os

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from deepagents import create_deep_agent

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")


@tool
def lookup_fact(topic: str) -> str:
    """Return a short canned fact about a topic (stands in for real research)."""
    facts = {
        "langgraph": "LangGraph models agents as stateful graphs of nodes and edges.",
        "deepagents": "Deep agents add planning, sub-agents, and a virtual filesystem to the loop.",
    }
    return facts.get(topic.lower(), f"No fact on file for '{topic}'.")


# Sub-agent: declarative dict form. `description` is a routing prompt the MAIN
# agent reads to decide when to delegate; `system_prompt` is self-contained
# because sub-agents do NOT inherit the parent's prompt.
research_subagent = {
    "name": "research-agent",
    "description": (
        "Delegate factual lookups to this subagent. Give it one topic at a time; "
        "it returns a one-sentence sourced fact, not raw notes."
    ),
    "system_prompt": (
        "You are a focused researcher. Use the lookup_fact tool for the given "
        "topic and return a single concise sentence — never raw notes."
    ),
    "tools": [lookup_fact],
}


def build_agent():
    model = init_chat_model(MODEL, model_provider="openai")
    return create_deep_agent(
        model=model,
        system_prompt=(
            "You coordinate research. When a user asks about a topic, delegate the "
            "lookup to the research-agent subagent, then relay its answer."
        ),
        subagents=[research_subagent],
    )


if __name__ == "__main__":
    agent = build_agent()

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "What is LangGraph? Delegate the lookup, then tell me."}]}
    )

    print("=== Final message ===")
    print(result["messages"][-1].content)

    print(
        "\nContext isolation: the research-agent ran the lookup_fact call in its own\n"
        "context window; only its final sentence returned to the coordinator, so the\n"
        "main agent's message list never saw the intermediate tool traffic."
    )
