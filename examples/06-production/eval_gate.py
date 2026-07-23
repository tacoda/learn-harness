"""The deploy gate from docs/06-production/05-maintenance-and-iteration.md (§③).

A CI-style regression gate: run a tiny LangSmith eval over a small dataset
against the deployable graph, compute an aggregate score, and exit non-zero if
it falls below a threshold. In a real pipeline this runs on every PR and blocks
promotion (staging -> prod) on a regression — evaluation *drives* development
rather than decorating it.

Real gates compare the candidate to the current production baseline; here we use
a fixed threshold so the example is self-contained and runnable on its own.

    uv run python eval_gate.py

Degrades gracefully (exit 0, skipped) when LANGSMITH_API_KEY is not set.
"""

import os
import sys
import uuid

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

# Regression threshold: fail the build below this fraction of examples passing.
THRESHOLD = 0.67


def main() -> int:
    if not os.environ.get("LANGSMITH_API_KEY"):
        print(
            "SKIPPED: LANGSMITH_API_KEY is not set. Set it in .env to run the "
            "eval gate (see .env.example). Not treating a skipped gate as a "
            "failure."
        )
        return 0

    from langsmith import Client

    from app.agent import graph

    client = Client()

    # A tiny dataset defined inline. In production this is *harvested* from real
    # traces (docs/06-production/05 §②) and pinned to a tagged version so the
    # gate's meaning does not drift; here we create a fresh one per run.
    examples = [
        {"inputs": {"question": "What's the status of order A1001?"},
         "outputs": {"expected": "shipped"}},
        {"inputs": {"question": "Can you check order A1002 for me?"},
         "outputs": {"expected": "delivered"}},
        {"inputs": {"question": "Where is order A1003?"},
         "outputs": {"expected": "cancelled"}},
    ]

    dataset_name = f"prod-gate-orders-{uuid.uuid4().hex[:8]}"
    dataset = client.create_dataset(dataset_name=dataset_name)
    client.create_examples(dataset_id=dataset.id, examples=examples)

    def target(inputs: dict) -> dict:
        """Run the deployable graph on one example."""
        result = graph.invoke(
            {"messages": [{"role": "user", "content": inputs["question"]}]}
        )
        return {"answer": result["messages"][-1].content}

    def resolves_order(outputs: dict, reference_outputs: dict) -> bool:
        """Pass if the reply states the expected order status."""
        answer = (outputs.get("answer") or "").lower()
        return reference_outputs["expected"].lower() in answer

    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=[resolves_order],
        experiment_prefix="prod-gate",
    )

    # Aggregate: fraction of rows whose evaluator scored truthy.
    scores = []
    for row in results:
        for r in row["evaluation_results"]["results"]:
            scores.append(1.0 if r.score else 0.0)

    if not scores:
        print("FAIL: eval produced no scores — cannot assess regression.")
        return 1

    score = sum(scores) / len(scores)
    print(f"Eval score: {score:.2f} over {len(scores)} case(s) "
          f"(threshold {THRESHOLD:.2f}).")

    if score < THRESHOLD:
        print("FAIL: score below threshold — blocking promotion.")
        return 1

    print("PASS: gate is green — safe to promote.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
