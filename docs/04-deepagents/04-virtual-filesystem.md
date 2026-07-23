# 04 · The Virtual Filesystem

## Mental model

A message list is a bad place to store working data. Everything you put there stays there, forever, on every subsequent model call — a 40 KB scraped webpage the agent needed once now rides along in the context for the rest of the run, crowding out the instructions and costing tokens every step. But the agent often *does* need to keep that data around; it just doesn't need it *in front of the model* the whole time.

The virtual filesystem solves this. The agent gets ordinary file tools — `ls`, `read_file`, `write_file`, `edit_file` (plus `glob` and `grep`) — that behave like a real filesystem from the model's point of view. It can dump a large intermediate result into a file, keep only a one-line acknowledgment in its context, and `read_file` it back later *only when it actually needs it*. Files become **external memory**: state the agent can address by name without paying to carry it in the context window.

The twist is in the word *virtual*. By default these files are not on your disk. They live in the agent's LangGraph state — a plain dictionary from path to contents. `write_file` mutates state; `read_file` reads it. Nothing touches the operating system. This is the "mocked-out virtual file system that uses the agent's state," and it is why file operations are safe by default: a hallucinated `write_file` can't clobber your home directory, only the agent's in-memory scratch space.

```
message list  = what the model sees every step   → keep this small
virtual files = addressable memory in state       → offload here, read back on demand
```

## In depth

The filesystem tools are supplied by `FilesystemMiddleware`, part of the default stack. Every deep agent has them; the middleware also appends usage instructions to the system prompt so the model knows the files exist and when to use them.

### The default backend: state

By default the filesystem is served by a `StateBackend` — a **thread-scoped** filesystem stored in the LangGraph state under a `files` key. Two consequences follow directly from "it's just state":

- **Persistence within a thread.** With a checkpointer attached, files written on one turn are still there on the next turn of the same `thread_id`, because the checkpointer persists the whole state (see `02-langgraph/05-persistence-checkpointers.md`). Follow-up turns can read files the agent wrote earlier in the conversation.
- **Isolation across threads.** A different `thread_id` gets a different state, hence a different, empty filesystem. Files are not shared between conversations.

You can seed the filesystem at invocation time by putting entries in the `files` field of the input state. Virtual paths start with `/`:

```python
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-5",
    backend=StateBackend(),          # the default; shown explicitly for clarity
    checkpointer=MemorySaver(),
)

result = agent.invoke(
    {
        "messages": [{"role": "user", "content": "Summarize the reference doc."}],
        "files": {                    # seed the in-state filesystem
            "/docs/reference.md": create_file_data("<file contents here>"),
        },
    },
    config={"configurable": {"thread_id": "conv-1"}},
)
# Files the agent wrote are available in result under the same "files" key.
```

`read_file` has built-in support for common image formats, returning them as multimodal content blocks — so "reading a file" can feed an image into a vision-capable model, not just text.

### Real backends when you want a real disk

The virtual filesystem is the *default*, not the only option. Filesystem tools operate through a pluggable **backend**, and `create_deep_agent` accepts a `backend=` argument. LangChain ships several:

- **`StateBackend`** — the default, in-state, thread-scoped, non-persistent beyond the checkpointer.
- **`FilesystemBackend`** — a *real* local filesystem rooted at a directory you specify. Now `write_file` genuinely writes to disk. This is where human-in-the-loop approval on writes stops being optional (see `05-customizing-and-middleware.md`).
- **Store-backed, sandbox, and composite backends** — persist to a LangGraph `store` for cross-session recall, run inside a sandbox that also exposes an `execute` tool for shell commands, or route different path prefixes to different backends via a composite router.

The model-facing tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`) are identical across backends. Swapping the backend changes *where the bytes go* without changing the agent's prompt or the model's behavior — the essence of the abstraction.

### Files as a context-engineering tool

The filesystem and sub-agents (`03-subagents-and-context-isolation.md`) are complementary moves in the same game. A common high-reliability pattern: a sub-agent does verbose research, writes its *full* findings to `/research/topic.md`, and returns only a short summary to the parent. The summary keeps the parent's context small; the file preserves the complete evidence so a later step (or a human) can consult it without it ever having lived in anyone's context window. The built-in prompt actively encourages this "offload tool outputs to disk" habit.

## Why it matters

This is the pillar that most directly attacks context bloat. Planning keeps the agent *oriented*; sub-agents keep noise *isolated*; the filesystem lets the agent *set data down and pick it back up* — the difference between an agent that must hold its entire working set in its head and one that can work against a scratchpad. It also makes the abstraction ladder explicit: the same tools that are a harmless in-memory mock in development become a real disk, a sandbox, or durable cross-session storage in production, purely by changing the backend. You develop safely and deploy for real without rewriting the agent.

## Pitfalls

- **Assuming files hit your disk.** The default is virtual, in-state, gone when the thread's state is gone. If you expected real files, you wanted `FilesystemBackend` (or a store/sandbox backend).
- **Expecting cross-thread or cross-session persistence for free.** `StateBackend` is thread-scoped. Files vanish for a new `thread_id`; for cross-session recall use a store-backed backend.
- **No checkpointer, no persistence.** Even within a thread, files only survive between turns because the checkpointer persists state. No checkpointer means every invocation starts empty.
- **Re-reading huge files into context.** Offloading to a file only helps if the agent reads back *selectively*. An agent that `read_file`s a giant file on every step has reintroduced the bloat it was trying to escape — prefer `grep`/`glob` to pull just the relevant slice.
- **Skipping approval on a real backend.** With `FilesystemBackend`, `write_file`/`edit_file` touch real disk. Gate them with human-in-the-loop (see next file).

## Exercises

1. Run a task that produces a large intermediate result. Confirm the agent writes it to a file and that your context/token usage stays flat compared with an agent that keeps everything in messages.
2. Invoke a deep agent with a seeded `files` entry and a task that requires reading it. Then inspect the returned state to see what files the agent added.
3. Attach a `MemorySaver` and a `thread_id`, have the agent write a file on turn one, then on turn two ask it to read that file back. Confirm it persists. Repeat with a new `thread_id` and confirm the file is gone.
4. Swap `StateBackend` for `FilesystemBackend` rooted at a temp directory and rerun. Verify the files now appear on real disk — and note why you'd want write approval before doing this in earnest.

## Further reading

- Deep Agents — backends (filesystem tools and pluggable backends): https://docs.langchain.com/oss/python/deepagents/backends
- Deep Agents — customization (StateBackend, FilesystemBackend, seeding files): https://docs.langchain.com/oss/python/deepagents/customization
- Deep Agents — context engineering: https://docs.langchain.com/oss/python/deepagents/context-engineering
- LangGraph persistence / checkpointers: https://docs.langchain.com/oss/python/langgraph/persistence
