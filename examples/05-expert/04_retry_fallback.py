"""Resilience wrappers: .with_retry(...) and .with_fallbacks([...]).

Demonstrates docs/05-expert/06-production-reliability.md (Resilience).

Any Runnable composes with resilience wrappers:

  * ``.with_retry(...)`` re-attempts *transient* faults (a 503, a flaky
    network) with bounded, backed-off retries.
  * ``.with_fallbacks([...])`` degrades on *persistent* faults — primary down,
    try a secondary, then a canned answer.

The first two demos use deterministic fake Runnables so retry and fallback are
provable without depending on real provider flakiness. The third composes both
wrappers on real models — the production idiom.
"""

import os

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableLambda

load_dotenv(find_dotenv())
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
CHEAP_MODEL = os.environ.get("CHEAP_MODEL", MODEL)

model = init_chat_model(MODEL, model_provider="openai")
cheap_model = init_chat_model(CHEAP_MODEL, model_provider="openai")


def make_flaky(fail_times: int):
    """A Runnable that raises the first `fail_times` calls, then succeeds."""
    state = {"calls": 0}

    def _fn(x):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise RuntimeError(f"transient failure #{state['calls']}")
        return f"ok after {state['calls']} attempt(s)"

    return RunnableLambda(_fn), state


if __name__ == "__main__":
    # 1) .with_retry: a transient fault is retried until it succeeds.
    flaky, calls = make_flaky(fail_times=2)
    resilient = flaky.with_retry(stop_after_attempt=3)
    out = resilient.invoke("go")
    print(f"with_retry: {out} (total attempts: {calls['calls']})")
    assert calls["calls"] == 3, "retry did not re-attempt the expected number of times"

    # 2) .with_fallbacks: a persistently-failing primary degrades to a fallback.
    broken_primary = RunnableLambda(lambda x: (_ for _ in ()).throw(RuntimeError("primary down")))
    fallback = RunnableLambda(lambda x: "answer from fallback")
    robust = broken_primary.with_fallbacks([fallback])
    result = robust.invoke("go")
    print(f"with_fallbacks: {result}")
    assert result == "answer from fallback", "fallback was not selected when primary failed"

    # 3) The production idiom: compose both on real models and invoke once.
    composed = model.with_retry(stop_after_attempt=3).with_fallbacks([cheap_model])
    assert hasattr(composed, "invoke"), "composed object is not a Runnable"
    reply = composed.invoke([{"role": "user", "content": "Reply with the single word: ready"}])
    print(f"composed model reply: {reply.content.strip()}")

    print("\nRetry and fallback wrappers constructed and invoked.")
