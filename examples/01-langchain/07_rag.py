"""Naive RAG: retriever + prompt + model in an LCEL chain grounded in retrieved context. Mirrors docs/01-langchain/07-rag-patterns.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

model = init_chat_model(MODEL, model_provider="openai")

SAMPLE_TEXT = """
Our refund window is 30 days from the date of purchase.
Refunds are issued to the original payment method within 5 business days.
Digital gift cards are non-refundable once redeemed.
To start a return, open your order history and click Request Refund.
""".strip()


def build_retriever():
    splitter = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=20)
    chunks = splitter.split_documents([Document(page_content=SAMPLE_TEXT)])
    store = InMemoryVectorStore.from_documents(
        chunks, embedding=OpenAIEmbeddings(model="text-embedding-3-small")
    )
    return store.as_retriever(search_kwargs={"k": 2})


def format_docs(docs) -> str:
    return "\n\n".join(d.page_content for d in docs)


if __name__ == "__main__":
    retriever = build_retriever()

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Answer using ONLY the context below. If it is not there, say you don't know.\n\n{context}"),
        ("user", "{question}"),
    ])

    # Canonical retrieval chain: dict literal -> RunnableParallel, RunnablePassthrough forwards the question.
    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | model
        | StrOutputParser()
    )

    answer = chain.invoke("What is our refund window?")
    print("answer ->", answer)
