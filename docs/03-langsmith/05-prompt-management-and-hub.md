# 05 · Prompt Management & Hub

## Mental model

The **prompt hub** is version control for prompts. Instead of a prompt string living as a literal in your code (and being re-deployed every time someone tweaks a word), it lives in LangSmith as a named, versioned object that your code **pulls** at runtime:

```
code  ──pull("joke-generator:production")──►  LangSmith hub
                                              (versioned prompt store)
```

The analogy is Git for prompts. Each named prompt is a repository; each save is a **commit** with a hash; **tags** (like `production`, `staging`) are movable pointers to specific commits. You push new versions, pull specific ones, and roll back by re-pointing a tag — all without touching or redeploying application code.

Why decouple prompts from code at all? Because prompt iteration and code iteration move at different speeds and are often done by different people. A product manager or prompt engineer can refine wording in the UI's playground and promote it to `production` without a code review, a build, or a deploy. The code just pulls whatever `production` currently points at.

## In depth

### Pushing a prompt

```python
from langsmith import Client
from langchain_core.prompts import ChatPromptTemplate

client = Client()
prompt = ChatPromptTemplate.from_template("tell me a joke about {topic}")

url = client.push_prompt("joke-generator", object=prompt)
print(url)   # link to the prompt in the UI
```

`push_prompt` creates the prompt on first call and adds a new commit on subsequent calls. Each push produces a commit hash. Prompts are private to your workspace by default; you can also publish to the public LangChain Hub for sharing.

### Pulling a prompt

```python
from langchain_openai import ChatOpenAI

prompt = client.pull_prompt("joke-generator")     # latest
model = ChatOpenAI(model="gpt-5.4-mini")
chain = prompt | model
chain.invoke({"topic": "cats"})
```

The pulled object is a real LangChain prompt template — it composes directly into a chain with `|`. That is the point: a managed prompt drops into the same code you would write with a hard-coded template, so adopting the hub is nearly zero-friction.

### Versions and tags

Pin to an exact commit for reproducibility, or to a tag for "whatever is blessed right now":

```python
# Exact commit hash — frozen, reproducible:
prompt = client.pull_prompt("joke-generator:12344e88")

# Tag — follows the pointer, updates when the tag moves:
prompt = client.pull_prompt("joke-generator:production")
```

If the `production` tag points at commit `12344e88`, the two calls above return the same thing *today* — but tomorrow, if someone re-points `production` to a new commit, the tagged pull follows it while the hash pull stays frozen. This is the core operational lever:

- **Production code pulls a tag** (`:production`) so you can promote a new prompt version by moving the tag — no deploy.
- **Reproducible experiments pin a hash** so an evaluation always uses the exact prompt it was run with.

### Using managed prompts in production code

The recommended pattern is to pull by tag at startup (or with a short cache) rather than on every request, so you are not hitting the hub in your hot path:

```python
_PROMPT = client.pull_prompt("support-bot:production")   # once, at boot

def handle(question: str):
    return (_PROMPT | model).invoke({"question": question})
```

Rolling out a new prompt is then: push the new version, test it (playground + an experiment from file 03), and move the `production` tag. Rolling back is moving the tag to the previous commit. Both are operations on data, not code.

### Collaboration and the playground

In the UI, prompts have a **playground**: edit the template, run it against sample inputs, tweak the model and parameters, and commit when satisfied. This is where non-engineers live. Teams typically wire it into a workflow: edits are committed to a `staging` tag, evaluated with a LangSmith experiment against a dataset, and only then promoted to `production`. Commits can trigger webhooks, so a promotion can kick off a CI eval automatically.

The collaboration win is separation of concerns: engineers own the code that *pulls* prompts; prompt authors own the *content* of prompts; the tag is the contract between them.

## Why it matters

Hard-coded prompts couple every wording change to your deploy pipeline and hide prompt history inside Git diffs that reviewers skim past. Managed prompts make prompt changes first-class: versioned, attributable, testable in isolation, promotable and revertible by moving a pointer. When a prompt change breaks production at 2am, "move the `production` tag back to the previous commit" is a far better recovery story than "revert the commit, rebuild, redeploy."

It also closes the loop with evaluation: because a prompt version is a stable, addressable artifact, you can run an experiment against `support-bot:staging`, get a score, and gate the promotion to `production` on that score.

## Pitfalls

- **Production pinned to a hash instead of a tag.** Pin a hash and you lose the promote-by-moving-a-tag workflow; every prompt change becomes a code change again. Pull a tag in production, pin hashes only for reproducible experiments.
- **Pulling on every request.** Hitting the hub in the hot path adds latency and a network dependency to each call. Pull at startup or cache with a short TTL.
- **Promoting without evaluating.** Moving `production` to an untested commit is shipping a prompt change blind. Run an experiment against the staging version first.
- **Losing the code/content contract.** If engineers start editing prompt content in the UI and authors start editing code, the separation of concerns collapses. Keep the tag as the interface.
- **Forgetting the network dependency.** A managed prompt means your app now depends on LangSmith being reachable at pull time. Cache the pulled prompt so a transient hub outage does not take down request handling.

## Exercises

1. Push a `ChatPromptTemplate` as `greeting-bot`, then push a modified version and confirm two commits exist with different hashes.
2. Tag one commit as `production`, pull by that tag and by its hash, and verify they return the same prompt. Then move the tag to the other commit and pull by tag again — observe it changed while the hash pull did not.
3. Pull a managed prompt, compose it into a chain with `prompt | model`, and invoke it. Explain why the pulled object slots in with no other code changes.
4. Sketch the promote-to-production workflow your team would use, naming where the eval gate (file 03) sits between `staging` and `production`.

## Further reading

- Prompt engineering overview: https://docs.langchain.com/langsmith/prompt-engineering
- Manage prompts (UI): https://docs.langchain.com/langsmith/manage-prompts
- Manage prompts programmatically: https://docs.langchain.com/langsmith/manage-prompts-programmatically
- Prompt hub / commits and tags: https://docs.langchain.com/langsmith/prompt-tags
