# 02 · Prompt Templates

## Mental model

A prompt template is a **`Runnable` that turns variables into messages**. It is the first link in most chains: `prompt | model | parser`. Keeping prompt construction as a declared, reusable object — rather than f-strings scattered through your code — means the same prompt can be versioned, composed, partially filled, and piped into any model.

## In depth

### ChatPromptTemplate

The workhorse. Declare messages with `{placeholder}` slots, then `.invoke` a dict of values to get a concrete message list:

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a {tone} assistant that answers in {language}."),
    ("user", "{question}"),
])

messages = prompt.invoke({"tone": "terse", "language": "English",
                          "question": "Why is the sky blue?"})
```

Each tuple is `(role, template)`. The result is a `PromptValue` you can pass straight to a model — or, more idiomatically, pipe:

```python
from langchain.chat_models import init_chat_model

chain = prompt | init_chat_model("claude-sonnet-4-6")
chain.invoke({"tone": "terse", "language": "English", "question": "Why is the sky blue?"})
```

The `|` composes both `Runnable`s into one. `chain.invoke` runs the prompt, feeds its output to the model, and returns the `AIMessage`.

### MessagesPlaceholder

When you need to splice in a *variable-length list* of messages — conversation history, few-shot exchanges, agent scratchpad — use a placeholder that expands to many messages:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    MessagesPlaceholder("history"),
    ("user", "{question}"),
])

prompt.invoke({
    "history": [("user", "Hi, I'm Bob."), ("assistant", "Hello Bob!")],
    "question": "What's my name?",
})
```

`MessagesPlaceholder("history")` expects the `history` key to be a list of messages and inlines them at that position. This is the mechanism for injecting chat history into a prompt.

### Template syntax: f-string vs. mustache

Default interpolation is Python `str.format` (`{var}`). If your prompt text contains literal braces (JSON examples, LaTeX), switch to mustache to avoid escaping every brace:

```python
prompt = ChatPromptTemplate.from_messages(
    [("user", "Return JSON like {{example}} for: {input}")],  # f-string: {{ }} escapes a literal brace
)

prompt = ChatPromptTemplate([("user", "Return JSON for: {{input}}")],
                            template_format="mustache")        # {{input}} is the variable
```

Pick one per template and be consistent. Mustache is the pragmatic choice for prompts heavy with literal braces.

### Partial

Pre-fill some variables and defer the rest — useful for values known at construction time (a date, a system role) versus call time (the user's question):

```python
from datetime import date

base = ChatPromptTemplate.from_messages([
    ("system", "Today is {today}. You are a {role}."),
    ("user", "{question}"),
])

support_prompt = base.partial(today=str(date.today()), role="support agent")
support_prompt.invoke({"question": "Where's my order?"})   # only 'question' left to supply
```

`.partial` returns a new template with fewer required variables. You can also pass a **callable** as a partial value to compute it lazily at invoke time (e.g. always-current timestamp).

### Few-shot prompt templates

To teach a task by example, format a list of input/output pairs into the prompt. Compose an example-formatting template with `FewShotChatMessagePromptTemplate`:

```python
from langchain_core.prompts import (
    ChatPromptTemplate, FewShotChatMessagePromptTemplate,
)

examples = [
    {"input": "2+2", "output": "4"},
    {"input": "3*3", "output": "9"},
]

example_prompt = ChatPromptTemplate.from_messages([
    ("user", "{input}"),
    ("assistant", "{output}"),
])

few_shot = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)

final = ChatPromptTemplate.from_messages([
    ("system", "You are a calculator. Answer with the number only."),
    few_shot,
    ("user", "{input}"),
])
```

`few_shot` expands into the two example exchanges as real messages. For example sets too large to include wholesale, pair it with an `example_selector` (e.g. semantic similarity) to pick the most relevant few per query.

## Why it matters

Templates separate **prompt structure from prompt data**. That separation is what makes prompts testable (invoke with fixtures), versionable (the template is an object, not string soup), swappable (same template, different model), and observable (LangSmith shows the rendered prompt as a discrete step). The tradeoff is a little indirection versus a raw f-string — paid back the first time you need to inject history, add few-shot examples, or reuse a prompt across chains.

## Pitfalls

- **Unescaped literal braces.** A JSON example in an f-string template throws `KeyError`. Escape as `{{ }}` or switch to `template_format="mustache"`.
- **Passing raw strings where a message list is expected.** `MessagesPlaceholder` needs a *list of messages*, not a string. Give it `[]` when there's no history yet, not `""`.
- **`PromptTemplate` vs. `ChatPromptTemplate`.** `PromptTemplate` yields a single string (for completion models); chat models want `ChatPromptTemplate`. Mixing them silently degrades your prompt to one flat user turn.
- **Old-tutorial `LLMChain(prompt=..., llm=...)`.** Dead in v1. The replacement is `prompt | model` — a plain `Runnable` pipe.
- **Hand-building the agent scratchpad.** With `create_agent` you do not assemble a scratchpad placeholder yourself; the agent manages its own message state. Templates-with-placeholders are for chains and for the *system* prompt, not for re-implementing the agent loop.

## Exercises

1. Build a `ChatPromptTemplate` with a system + user message and two variables; pipe it to a model and invoke.
2. Add a `MessagesPlaceholder("history")` and run two turns, passing the first turn's messages into the second.
3. Use `.partial` with a callable that injects the current timestamp, and confirm it updates across two invocations seconds apart.
4. Write a `FewShotChatMessagePromptTemplate` for a 2-example classification task and verify the examples appear as messages via `prompt.invoke(...)`.

## Further reading

- Prompt templates: https://docs.langchain.com/oss/python/langchain/prompt-templates
- Messages: https://docs.langchain.com/oss/python/langchain/messages
- LCEL / composition: https://docs.langchain.com/oss/python/langchain/lcel
