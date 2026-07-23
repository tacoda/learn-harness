"""Regression test via the langsmith[pytest] integration.

Mirrors docs/03-langsmith/08-testing-in-ci-cd.md.

Each @pytest.mark.langsmith test syncs to LangSmith as a tracked case: the
pass/fail status is auto-logged under the 'pass' feedback key, and the
t.log_* helpers record inputs/outputs/feedback. The plain `assert` is still the
gate. Run with:  uv run pytest --langsmith-output

Requires LANGSMITH_API_KEY and OPENAI_API_KEY in the root .env.
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

import pytest
from langchain_openai import ChatOpenAI
from langsmith import testing as t

llm = ChatOpenAI(model=MODEL, temperature=0)


def classify_sentiment(text: str) -> str:
    """Return 'positive' or 'negative' for the given text."""
    prompt = (
        "Classify the sentiment of the text as exactly one word, either "
        f"'positive' or 'negative'. Respond with only that word.\n\n{text}"
    )
    return llm.invoke(prompt).content.strip().lower()


@pytest.mark.langsmith
def test_positive_sentiment() -> None:
    text = "I absolutely love this product, it works perfectly!"
    t.log_inputs({"text": text})
    t.log_reference_outputs({"sentiment": "positive"})

    sentiment = classify_sentiment(text)
    t.log_outputs({"sentiment": sentiment})

    t.log_feedback(key="matched", score=int(sentiment == "positive"))
    assert "positive" in sentiment


@pytest.mark.langsmith
def test_negative_sentiment() -> None:
    text = "This is the worst experience I have ever had. Terrible."
    t.log_inputs({"text": text})
    t.log_reference_outputs({"sentiment": "negative"})

    sentiment = classify_sentiment(text)
    t.log_outputs({"sentiment": sentiment})

    t.log_feedback(key="matched", score=int(sentiment == "negative"))
    assert "negative" in sentiment
