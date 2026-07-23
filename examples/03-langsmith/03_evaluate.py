"""Run an experiment: a target over a dataset scored by a heuristic evaluator.

Mirrors docs/03-langsmith/03-evaluation-and-experiments.md.

Defines target(inputs) -> dict that calls the model, a reference-based heuristic
evaluator with the fixed (inputs, outputs, reference_outputs) signature, and runs
client.evaluate over the "Support QA" dataset created by 02_dataset.py. Prints
the resulting experiment name.

Requires LANGSMITH_API_KEY and OPENAI_API_KEY in the root .env.
Run 02_dataset.py first so the dataset exists.
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain_openai import ChatOpenAI
from langsmith import Client

DATASET_NAME = "Support QA"

llm = ChatOpenAI(model=MODEL, temperature=0)


def target(inputs: dict) -> dict:
    """The system under test: answer the question, return a dict."""
    question = inputs["question"]
    prompt = (
        "Answer the support question as briefly as possible — ideally a single "
        f"word or short phrase, no punctuation beyond what is needed.\n\n{question}"
    )
    answer = llm.invoke(prompt).content
    return {"answer": answer}


def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Heuristic: does the model's answer contain the reference answer?

    Cheap, deterministic substring check — no LLM needed. Case-insensitive so
    "Paris" matches "The capital is Paris.".
    """
    expected = reference_outputs["answer"].strip().lower()
    actual = outputs["answer"].strip().lower()
    score = 1.0 if expected in actual else 0.0
    return {"key": "correctness", "score": score}


def main() -> None:
    client = Client()
    results = client.evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[correctness],
        experiment_prefix=f"{MODEL}-heuristic",
        max_concurrency=4,
    )
    print(f"Experiment: {results.experiment_name}")
    print("Open https://smith.langchain.com to inspect per-example scores under")
    print("the 'correctness' feedback column.")


if __name__ == "__main__":
    main()
