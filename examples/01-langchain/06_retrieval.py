"""Retrieval: split, embed into an InMemoryVectorStore, and retrieve. Mirrors docs/01-langchain/06-retrieval-embeddings-vectorstores.md."""
import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

SAMPLE_TEXT = """
LangChain is a framework for building applications with large language models.
A chat model is a function from a list of messages to a message.
Retrieval puts your own data in front of a model: load, split, embed, and store.
An embeddings model maps text to a vector; semantically similar text lands nearby.
A vector store holds those vectors and does nearest-neighbor search.
To reset your password, open Settings, choose Security, and click Reset Password.
""".strip()


def build_retriever():
    """The four stages: split text into chunks, embed each chunk, store the vectors, expose a retriever."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=20)
    chunks = splitter.split_documents([Document(page_content=SAMPLE_TEXT)])
    assert len(chunks) > 1, "splitter should produce more than one chunk from the sample"
    print("split ->", len(chunks), "chunks")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    store = InMemoryVectorStore.from_documents(chunks, embedding=embeddings)
    return store.as_retriever(search_kwargs={"k": 2})


if __name__ == "__main__":
    retriever = build_retriever()
    hits = retriever.invoke("How do I reset my password?")
    assert hits, "retriever should return at least one Document"
    print("retrieved ->", len(hits), "hits")
    for i, doc in enumerate(hits, 1):
        print(f"  {i}. {doc.page_content.strip()}")
