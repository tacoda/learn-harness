# 03 · Structured Output

## Mental model

Structured output is how you turn a chat model from a **text generator** into a **typed function**: you hand it a schema (usually a Pydantic model) and get back a validated instance instead of a string you have to parse. Two mechanisms deliver it — a **model-level** wrapper (`with_structured_output`) for one-shot extraction, and an **agent-level** `response_format` (`ToolStrategy` / `ProviderStrategy`) for an agent's final answer.

## In depth

### Model level: `with_structured_output`

Wrap a model with a schema; the returned `Runnable` yields instances of that schema:

```python
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

class Contact(BaseModel):
    name: str = Field(description="Full name of the person")
    email: str
    phone: str | None = None

model = init_chat_model("claude-sonnet-4-6")
extractor = model.with_structured_output(Contact)

result = extractor.invoke("Reach John Doe at john@example.com or (555) 123-4567.")
print(result.name, result.email)   # -> John Doe john@example.com
print(type(result))                # -> <class '...Contact'>
```

The `Field(description=...)` text is sent to the model as part of the schema — treat it as prompt real estate, not decoration. It's the single biggest lever on extraction accuracy. This is the right tool when the *entire* job is "read text → emit a typed record."

### Agent level: `response_format`

An agent runs a loop (model → tools → model → …). To make its **final** message a typed object rather than prose, pass `response_format`. The parsed value lands in `result["structured_response"]`:

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel

class Weather(BaseModel):
    temperature: float
    condition: str

def weather_tool(location: str) -> str:
    """Get the weather at a location."""
    return "Sunny and 75 degrees F."

agent = create_agent(
    model="claude-sonnet-4-6",
    tools=[weather_tool],
    response_format=ToolStrategy(Weather),
)

result = agent.invoke({"messages": [{"role": "user", "content": "Weather in SF?"}]})
result["structured_response"]      # -> Weather(temperature=75.0, condition='Sunny')
```

### ToolStrategy vs. ProviderStrategy

`response_format` accepts two strategies, and the choice is a real tradeoff:

| | `ToolStrategy` | `ProviderStrategy` |
|---|---|---|
| How | Presents the schema as a synthetic *tool*; the model "calls" it to answer | Uses the provider's native structured-output / JSON-schema mode |
| Portability | Works with **any** tool-calling model | Only providers that support native structured output |
| Reliability | Depends on tool-calling quality; can be retried | Provider guarantees schema conformance |
| Cost | An extra tool round-trip | Usually none |

```python
from langchain.agents.structured_output import ToolStrategy, ProviderStrategy

response_format=ToolStrategy(Weather)      # portable default
response_format=ProviderStrategy(Weather)  # when the provider supports it natively
```

Rule of thumb: `ProviderStrategy` when your chosen provider supports it (fewer failure modes); `ToolStrategy` when you want provider-portable code or the model lacks native structured output.

### Handling failures and retries

Structured output *can* fail — the model returns malformed JSON or a value that won't validate. `ToolStrategy` exposes handling for this so a bad emission becomes a ret/correction rather than an exception:

```python
from langchain.agents.structured_output import ToolStrategy

response_format = ToolStrategy(
    Weather,
    handle_errors="Return valid data matching the schema.",  # feed the error back to the model to retry
)
```

`handle_errors` can be a bool, a message string, an exception type, or a callable — the pattern is: on validation failure, send the model a corrective message and let it try again rather than crashing the run.

### Multiple possible shapes

When the answer could be one of several types, give the model a **union**. With Pydantic, wrap the alternatives:

```python
from typing import Union
from pydantic import BaseModel

class Weather(BaseModel):
    temperature: float

class ErrorReply(BaseModel):
    reason: str

response_format = ToolStrategy(Union[Weather, ErrorReply])
```

The model picks the branch that fits, and you `isinstance`-dispatch on the result. This is the clean way to model "answer *or* refuse/clarify."

## Why it matters

Structured output is the boundary between an LLM and the rest of your program. Downstream code wants a `Contact`, not a paragraph — validated types let you fail fast at the seam instead of debugging a regex three functions deep. The `with_structured_output` vs. `response_format` split mirrors the chain-vs-agent split: use the model wrapper when there's no tool loop, use `response_format` when there is and you want the loop's *conclusion* typed. Choosing `ToolStrategy` vs. `ProviderStrategy` is choosing portability vs. provider-native guarantees — a decision you can revisit per model without touching your schema.

## Pitfalls

- **Empty or missing field descriptions.** The model can't infer that `phone` means E.164. Descriptions are prompt, not comments — write them.
- **Reaching for `response_format` when there's no agent loop.** For pure extraction, `model.with_structured_output(...)` is simpler and cheaper. `response_format` is for `create_agent`.
- **Reading the wrong key.** The agent's typed result is at `result["structured_response"]`, not `result["messages"][-1]`.
- **The old `response_format={"type": "json_object"}` dict hack.** Replaced by `ToolStrategy` / `ProviderStrategy`. Raw-dict tutorials predate v1.
- **Assuming structured output never fails.** `ToolStrategy` can produce invalid data on hard schemas. Set `handle_errors` for anything user-facing.
- **Over-deep nested schemas.** Extraction accuracy drops as nesting grows. Flatten where you can; validate what you get.

## Exercises

1. Extract a `Contact` from a messy sentence with `with_structured_output`; then delete the field descriptions and observe accuracy change.
2. Build an agent with a tool and a `ToolStrategy` response format; read `result["structured_response"]`.
3. Switch that agent to `ProviderStrategy` and note which providers accept it and which error.
4. Define a `Union[Answer, Clarification]` response format and craft one prompt that triggers each branch.

## Further reading

- Structured output: https://docs.langchain.com/oss/python/langchain/structured-output
- `create_agent` structured responses: https://docs.langchain.com/oss/python/langchain/agents
- Models (`with_structured_output`): https://docs.langchain.com/oss/python/langchain/models
