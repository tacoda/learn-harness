"""Create a dataset and examples, then read them back.

Mirrors docs/03-langsmith/02-datasets.md.

Uses Client() to create (idempotently) a small "Support QA" dataset, add a few
{"inputs": ..., "outputs": ...} examples, then list_examples and confirm the
count. This dataset is the fixture that 03_evaluate.py and 04_llm_judge.py
evaluate against, so run this first.

Requires LANGSMITH_API_KEY in the root .env.
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langsmith import Client

DATASET_NAME = "Support QA"

EXAMPLES = [
    {"inputs": {"question": "How many users on the Starter plan?"},
     "outputs": {"answer": "5"}},
    {"inputs": {"question": "How do I reset my password?"},
     "outputs": {"answer": "Click 'Forgot password' on the login page."}},
    {"inputs": {"question": "What is the capital of France?"},
     "outputs": {"answer": "Paris"}},
]


def ensure_dataset(client: Client) -> None:
    """Create the dataset + examples only if it does not already exist."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        return
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Golden questions for the support bot",
    )
    client.create_examples(dataset_id=dataset.id, examples=EXAMPLES)


def main() -> None:
    client = Client()
    ensure_dataset(client)

    examples = list(client.list_examples(dataset_name=DATASET_NAME))
    count = len(examples)

    print(f"Dataset: {DATASET_NAME!r}")
    print(f"Examples in dataset: {count}")
    for ex in examples:
        print(f"  - {ex.inputs} -> {ex.outputs}")

    # Self-check: a freshly created dataset holds exactly our seed examples.
    # (If the dataset pre-existed with extra rows, it is at least as large.)
    assert count >= len(EXAMPLES), (
        f"expected >= {len(EXAMPLES)} examples, found {count}"
    )
    print(f"\nOK: dataset has at least the {len(EXAMPLES)} seed examples.")


if __name__ == "__main__":
    main()
