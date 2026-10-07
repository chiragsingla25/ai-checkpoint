# AI Checkpoint: refined idea (v0.2, 2026-10-07)

Supersedes the capture-first design in `MVP.md` for the first build. `MVP.md` stays as the long-term vision; the parts deferred from it are in `ROADMAP.md`.

## The problem, in one sentence

A long Claude or ChatGPT chat gets heavy, and when you open a new chat you cannot pick up from the exact step you were on, and you cannot go back to an earlier step and try a different direction.

## The idea

Named restore points for AI chats, saved and restored from inside the chat through one MCP server.

```
Heavy chat ──"checkpoint this as forecasting-v2"──► save_checkpoint
                                                         │  (the model compacts the chat
                                                         │   into fixed sections)
                                                         ▼
                                     ~/.ai-checkpoint  (JSON + one git commit per save)
                                                         │
New chat ───"resume forecasting-v2"───► resume_checkpoint ┘ → continuation brief
                                                         → the new chat carries on from that step
```

Key insight: the model in the current chat already has the whole conversation in context, so it is the best compactor. No transcript capture, no hooks, no browser extension. The MCP tool's input schema *is* the compaction format, so every model that calls it must fill the same sections.

## The compaction format (what a checkpoint holds)

| Section | Why it exists |
|---|---|
| `objective` | What the work is for. |
| `context` | Background facts, constraints and preferences the user stated. |
| `decisions` | Each decision with its reason, so the new chat does not reopen settled questions. |
| `completed` | What is done. |
| `current_step` | The exact step the chat was on when saved. |
| `next_steps` | Ordered, step-by-step instructions to continue. |
| `open_questions` | Unresolved items. |
| `verbatim` | Things that must not be paraphrased: code, numbers, exact wording, file contents. Each with a label. |
| `last_exchange` | The last user message and assistant reply, word for word. |
| `notes_for_next_ai` | Anything else the saving model thinks the next chat must know. |

Plus metadata: `chat_name`, `checkpoint_name`, `checkpoint_id`, `created_at`, `client` (e.g. claude.ai, chatgpt, claude-code), `resumed_from` (the checkpoint this chat was resumed from, which gives a branch tree).

## Interface (one MCP server)

- `save_checkpoint(chat_name, checkpoint_name, <sections>, client?, resumed_from?)` → id, commit.
- `list_checkpoints(chat_name?)` → checkpoints, newest first, grouped by chat.
- `get_checkpoint(ref)` → the stored checkpoint.
- `resume_checkpoint(ref)` → a continuation brief: "You are continuing from checkpoint X…", sections in a fixed order, verbatim blocks intact, and an instruction to confirm the current step before continuing.
- An MCP **prompt** `resume` (user-picked from the client's menu) that returns the same brief.

`ref` can be a checkpoint id (`cp-007`), a checkpoint name, or `chat_name/checkpoint_name`.

## What makes it different from what exists

See `research.md`. Extensions (Thredly, MemoryPlugin, Continue AI, ThreadPort), skills (/handoff) and MCP servers (Session Handoff, Memo) do one-shot compaction or latest-only saves. This combines:

1. Named, versioned restore points per chat, with a branch tree (`resumed_from`).
2. Invoked from inside the chat (no extension, no copy-paste).
3. Same store across clients.
4. A published evaluation of handover quality: checkpoint vs. plain summary vs. full history.

## First build scope

1. Checkpoint format, validation and storage with git.
2. Local MCP server (stdio) for Claude Desktop / Claude Code / any local MCP client, plus a thin CLI for testing.
3. Handover evaluation kit (offline-testable, with real-model adapters when an API key is present).

Everything else is in `ROADMAP.md`.
