"""Tracing & observability with @traceable and wrap_openai.

Mirrors docs/03-langsmith/01-tracing-and-observability.md and
docs/03-langsmith/09-instrumenting-your-code-traceable.md.

Instruments a plain (non-LangChain) pipeline two ways: a wrapped OpenAI client
whose calls become `llm` runs automatically, and a @traceable function that
becomes the parent `chain` run. Running this with LANGSMITH_TRACING=true
produces one nested trace in the configured LANGSMITH_PROJECT.

Requires LANGSMITH_API_KEY and OPENAI_API_KEY in the root .env
(plus LANGSMITH_TRACING=true and, optionally, LANGSMITH_PROJECT).
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI

# A wrapped client: every call it makes is captured as an `llm` run with
# token counts and cost, no per-call code needed.
client = wrap_openai(OpenAI())


@traceable(run_type="prompt")
def build_messages(question: str) -> list[dict]:
    return [
        {"role": "system", "content": "Answer in one short sentence."},
        {"role": "user", "content": question},
    ]


@traceable  # defaults: run_type="chain", name="ask"
def ask(question: str) -> str:
    """Parent run. build_messages and the wrapped LLM call nest underneath."""
    messages = build_messages(question)
    completion = client.chat.completions.create(model=MODEL, messages=messages)
    return completion.choices[0].message.content


def main() -> None:
    project = os.environ.get("LANGSMITH_PROJECT", "default")
    question = "What is LangSmith in one sentence?"
    answer = ask(question)

    print(f"Q: {question}")
    print(f"A: {answer}")
    print()
    print(f"Trace sent to LangSmith project: {project!r}")
    print("Open https://smith.langchain.com and find the 'ask' run to see the")
    print("nested tree: ask (chain) -> build_messages (prompt) + the LLM call.")
    if os.environ.get("LANGSMITH_TRACING", "").lower() != "true":
        print()
        print("NOTE: LANGSMITH_TRACING is not 'true' — the code ran but emitted")
        print("no trace. Set LANGSMITH_TRACING=true in .env to capture it.")


if __name__ == "__main__":
    main()
