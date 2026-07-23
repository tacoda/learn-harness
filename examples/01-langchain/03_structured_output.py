"""Structured output: with_structured_output turns a model into a typed function. Mirrors docs/01-langchain/03-structured-output.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from pydantic import BaseModel, Field

from langchain.chat_models import init_chat_model

model = init_chat_model(MODEL, model_provider="openai")


class Contact(BaseModel):
    """A person's contact details extracted from free text."""

    name: str = Field(description="Full name of the person")
    email: str = Field(description="Email address")
    phone: str | None = Field(default=None, description="Phone number, digits only if present")


def demo_extract() -> Contact:
    """The wrapped Runnable yields validated instances of the schema, not strings."""
    extractor = model.with_structured_output(Contact)
    result = extractor.invoke("Reach John Doe at john@example.com or (555) 123-4567.")
    # Field descriptions are prompt real estate and drive extraction accuracy.
    assert isinstance(result, Contact), "with_structured_output must return a Contact instance"
    assert isinstance(result.name, str), "name field must be typed as str"
    print("extract ->", result)
    print("types   ->", type(result).__name__, "| name:", type(result.name).__name__)
    return result


if __name__ == "__main__":
    demo_extract()
