"""Prompt templates: MessagesPlaceholder, piping to a model, and partials. Mirrors docs/01-langchain/02-prompt-templates.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from datetime import date

from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

model = init_chat_model(MODEL, model_provider="openai")

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Today is {today}."),
    MessagesPlaceholder("history"),
    ("user", "{question}"),
])


def demo_render() -> None:
    """Invoking a template turns variables into a concrete message list (a PromptValue)."""
    value = prompt.invoke({
        "today": str(date.today()),
        "history": [("user", "Hi, I'm Bob."), ("assistant", "Hello Bob!")],
        "question": "What's my name?",
    })
    messages = value.to_messages()
    # system + 2 history + user == 4 messages once the placeholder expands.
    assert len(messages) == 4, f"expected 4 rendered messages, got {len(messages)}"
    print("render -> rendered", len(messages), "messages")


def demo_chain() -> None:
    """prompt | model composes both Runnables; invoke runs the prompt then the model."""
    chain = prompt | model
    response = chain.invoke({
        "today": str(date.today()),
        "history": [("user", "Hi, I'm Bob."), ("assistant", "Hello Bob!")],
        "question": "What's my name? Answer with just the name.",
    })
    print("chain ->", response.content)


def demo_partial() -> None:
    """partial pre-fills variables known at construction time, leaving the rest for call time."""
    support = prompt.partial(today=str(date.today()), history=[])
    response = (support | model).invoke({"question": "Reply with the single word: ready."})
    print("partial ->", response.content)


if __name__ == "__main__":
    demo_render()
    demo_chain()
    demo_partial()
