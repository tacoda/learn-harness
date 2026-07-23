"""Mirrors docs/04-deepagents/04-virtual-filesystem.md.

Deep agents ship state-backed filesystem tools (ls / read_file / write_file /
edit_file). By default the "files" live in the agent's LangGraph state — a dict
from path -> FileData — not on real disk. We task the agent to write a file,
then read the returned state's "files" key and print the contents. `FileData` is
a TypedDict ({content, encoding, ...}); `file_data_to_string` decodes it.
"""

import os

from dotenv import load_dotenv, find_dotenv
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent
from deepagents.backends.utils import file_data_to_string

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

TARGET = "/notes/haiku.txt"


def build_agent():
    model = init_chat_model(MODEL, model_provider="openai")
    return create_deep_agent(
        model=model,
        system_prompt=(
            "You are a note-taker. When asked to save text, use the write_file tool "
            "to write it to the exact path requested, then confirm."
        ),
    )


if __name__ == "__main__":
    agent = build_agent()

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"Write a two-line haiku about autumn to the file {TARGET} using write_file.",
                }
            ]
        }
    )

    files = result.get("files", {})
    print("=== Files in returned state ===")
    for path in files:
        print(f"  {path}")

    # Self-check: the agent should have written to the virtual filesystem in state.
    assert TARGET in files, f"expected {TARGET} in returned state's files, got {list(files)}"
    print(f"\nself-check ok: {TARGET} exists in state.files")

    print(f"\n=== Contents of {TARGET} ===")
    print(file_data_to_string(files[TARGET]))
