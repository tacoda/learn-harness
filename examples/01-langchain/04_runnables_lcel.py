"""Runnables & LCEL: pipe composition, RunnableParallel, and batch. Mirrors docs/01-langchain/04-runnables-and-lcel.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel

model = init_chat_model(MODEL, model_provider="openai")


def demo_pipe() -> None:
    """prompt | model | StrOutputParser() is itself a Runnable that returns a plain string."""
    prompt = ChatPromptTemplate.from_messages([("user", "Explain {topic} in one sentence.")])
    chain = prompt | model | StrOutputParser()
    out = chain.invoke({"topic": "entropy"})
    assert isinstance(out, str), "StrOutputParser must yield a plain string"
    print("pipe ->", out)


def demo_parallel() -> None:
    """RunnableParallel fans one input out to several branches, collecting a dict; branches run concurrently."""
    joke = ChatPromptTemplate.from_messages([("user", "Tell a one-line joke about {topic}.")]) | model | StrOutputParser()
    fact = ChatPromptTemplate.from_messages([("user", "State one fact about {topic}.")]) | model | StrOutputParser()
    branches = RunnableParallel(joke=joke, fact=fact)
    result = branches.invoke({"topic": "octopuses"})
    assert "joke" in result and "fact" in result, "both parallel branch keys must be present"
    print("parallel keys ->", sorted(result))
    print("  joke ->", result["joke"])
    print("  fact ->", result["fact"])


def demo_batch() -> None:
    """A composed chain is a Runnable, so it speaks .batch too."""
    chain = ChatPromptTemplate.from_messages([("user", "Capital of {country}? One word.")]) | model | StrOutputParser()
    outs = chain.batch([{"country": "France"}, {"country": "Japan"}])
    assert len(outs) == 2, "batch must return one result per input"
    print("batch ->", outs)


if __name__ == "__main__":
    demo_pipe()
    demo_parallel()
    demo_batch()
