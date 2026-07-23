"""LLM-as-judge evaluation with openevals' CORRECTNESS_PROMPT.

Mirrors docs/03-langsmith/04-evaluators-llm-as-judge.md.

Wraps openevals' create_llm_as_judge (with the vetted CORRECTNESS_PROMPT) in a
normal evaluator function and passes it to client.evaluate — the semantic
counterpart to the heuristic evaluator in 03_evaluate.py. A judge grades whether
the answer is correct against the reference, which catches paraphrases a
substring check would miss.

Requires LANGSMITH_API_KEY and OPENAI_API_KEY in the root .env.
Run 02_dataset.py first so the dataset exists.
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

from langchain_openai import ChatOpenAI
from langsmith import Client
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

DATASET_NAME = "Support QA"

llm = ChatOpenAI(model=MODEL, temperature=0)

# The judge model — reuse MODEL via openevals' "openai:<model>" form.
judge = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT,
    model=f"openai:{MODEL}",
    feedback_key="correctness",
)


def target(inputs: dict) -> dict:
    question = inputs["question"]
    answer = llm.invoke(f"Answer the support question briefly:\n\n{question}").content
    return {"answer": answer}


def correctness_judge(inputs: dict, outputs: dict, reference_outputs: dict):
    """LLM-as-judge evaluator: grades output against the reference answer."""
    return judge(
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )


def main() -> None:
    client = Client()
    results = client.evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[correctness_judge],
        experiment_prefix=f"{MODEL}-llm-judge",
        max_concurrency=4,
    )
    print(f"Experiment: {results.experiment_name}")
    print("Open https://smith.langchain.com to read the judge's per-example")
    print("score and comment under the 'correctness' feedback column.")


if __name__ == "__main__":
    main()
