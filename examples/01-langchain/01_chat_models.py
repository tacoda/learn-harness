"""Chat models: invoke, stream, batch, and message forms. Mirrors docs/01-langchain/01-chat-models-and-messages.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, SystemMessage, HumanMessage

model = init_chat_model(MODEL, model_provider="openai")


def demo_invoke() -> None:
    """One call, one AIMessage. Message objects carry role via their type."""
    messages = [
        SystemMessage("You are a terse assistant. One sentence maximum."),
        HumanMessage("Why is the sky blue?"),
    ]
    response = model.invoke(messages)
    assert isinstance(response, AIMessage), "model.invoke must return an AIMessage"
    print("invoke ->", response.content)


def demo_message_forms() -> None:
    """Message objects, OpenAI-style dicts, and a bare string all normalize the same."""
    from_objects = model.invoke([HumanMessage("Say 'ok'.")])
    from_dicts = model.invoke([{"role": "user", "content": "Say 'ok'."}])
    from_string = model.invoke("Say 'ok'.")
    for r in (from_objects, from_dicts, from_string):
        assert isinstance(r, AIMessage), "all three input forms must produce an AIMessage"
    print("message forms -> all three inputs produced an AIMessage")


def demo_stream() -> None:
    """stream yields AIMessageChunks token-by-token; lowers latency to first token."""
    print("stream -> ", end="", flush=True)
    for chunk in model.stream("List three primary colors, comma separated."):
        print(chunk.text, end="", flush=True)
    print()


def demo_batch() -> None:
    """batch runs independent inputs concurrently, results in input order."""
    results = model.batch(["Capital of France?", "Capital of Japan?"])
    assert len(results) == 2, "batch must return one result per input, in order"
    print("batch ->", [r.content for r in results])


if __name__ == "__main__":
    demo_invoke()
    demo_message_forms()
    demo_stream()
    demo_batch()
