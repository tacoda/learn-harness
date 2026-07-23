"""Measuring cost & latency: naive vs. a cheap-model prefilter.

Demonstrates docs/05-expert/07-cost-and-latency-optimization.md
(Model selection and tiering).

The task: answer a batch of queries. The *naive* approach sends every query to
the strong model. The *optimized* approach uses a cheap model to prefilter each
query — trivial queries are answered by the cheap model, and only genuinely
hard ones escalate to the strong model.

Each approach is timed with ``time.perf_counter`` and its token usage summed
via ``response.usage_metadata`` into a rough cost estimate, then printed as a
small comparison table. CHEAP_MODEL and MODEL both default to MODEL.
"""

import os
import time
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
CHEAP_MODEL = os.environ.get("CHEAP_MODEL", MODEL)

strong = init_chat_model(MODEL, model_provider="openai")
cheap = init_chat_model(CHEAP_MODEL, model_provider="openai")

# Rough USD per-token prices (input, output). Defaults cover gpt-4o-mini.
PRICES = {
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
}
DEFAULT_PRICE = PRICES["gpt-4o-mini"]

QUERIES = [
    "What is 2 + 2?",
    "Say hello.",
    "What is the capital of France?",
    "Explain, in two sentences, why distributed consensus is hard.",
]


class Difficulty(BaseModel):
    """Cheap prefilter verdict."""

    level: Literal["trivial", "hard"] = Field(
        description="'trivial' if a small model can answer perfectly, else 'hard'"
    )


prefilter = cheap.with_structured_output(Difficulty)


def cost_of(model_name: str, usage: dict) -> float:
    in_price, out_price = PRICES.get(model_name, DEFAULT_PRICE)
    return usage.get("input_tokens", 0) * in_price + usage.get("output_tokens", 0) * out_price


def run_naive() -> dict:
    """Every query goes to the strong model."""
    cost, strong_calls = 0.0, 0
    for q in QUERIES:
        resp = strong.invoke([{"role": "user", "content": q}])
        strong_calls += 1
        cost += cost_of(MODEL, resp.usage_metadata or {})
    return {"strong_calls": strong_calls, "cost": cost}


def run_optimized() -> dict:
    """Cheap prefilter decides; trivial stays cheap, hard escalates."""
    cost, strong_calls = 0.0, 0
    for q in QUERIES:
        verdict = prefilter.invoke(
            [{"role": "user", "content": f"How hard is this query to answer?\n{q}"}]
        )
        if verdict.level == "hard":
            resp = strong.invoke([{"role": "user", "content": q}])
            strong_calls += 1
            cost += cost_of(MODEL, resp.usage_metadata or {})
        else:
            resp = cheap.invoke([{"role": "user", "content": q}])
            cost += cost_of(CHEAP_MODEL, resp.usage_metadata or {})
    return {"strong_calls": strong_calls, "cost": cost}


def timed(fn) -> dict:
    start = time.perf_counter()
    out = fn()
    out["latency"] = time.perf_counter() - start
    return out


if __name__ == "__main__":
    naive = timed(run_naive)
    optimized = timed(run_optimized)

    print(f"Task: answer {len(QUERIES)} queries.  strong={MODEL}  cheap={CHEAP_MODEL}\n")
    header = f"{'approach':<12}{'latency (s)':>13}{'strong calls':>14}{'est. cost ($)':>16}"
    print(header)
    print("-" * len(header))
    for name, r in (("naive", naive), ("optimized", optimized)):
        print(f"{name:<12}{r['latency']:>13.2f}{r['strong_calls']:>14}{r['cost']:>16.6f}")

    # The prefilter must not increase strong-model calls beyond the naive path.
    assert optimized["strong_calls"] <= naive["strong_calls"], "prefilter increased strong-model usage"
    print("\nOptimized path used no more strong-model calls than naive.")
