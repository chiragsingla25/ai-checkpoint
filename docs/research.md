# Research notes (2026-10-07)

Input for intake. Facts gathered from public docs; verify against a real local session before relying on exact field names.

## Capture: Claude Code (first provider)

- Transcripts live at `~/.claude/projects/<project-slug>/<session-id>.jsonl`, one JSON object per line.
- Relevant line types: `"type": "user"` and `"type": "assistant"`, each with `uuid`, `parentUuid`, `sessionId`, `timestamp` (ISO 8601), `cwd`, and `message` = `{role, content}`.
  - `message.content` is either a string or a list of blocks: `{"type":"text","text":...}`, `{"type":"tool_use",...}`, `{"type":"tool_result",...}`, `{"type":"thinking",...}`.
  - A `"user"` line whose content is only `tool_result` blocks is a tool result, not something the human typed.
  - Other line types exist (`summary`, `system`, `file-history-snapshot`, ...) and must be skipped without failing.
  - An assistant turn may be split across several lines sharing the same `message.id`; text blocks should be merged in order.
- Hooks (configured in `.claude/settings.json` or `~/.claude/settings.json`) give every hook stdin JSON with `session_id`, `transcript_path`, `cwd`, `hook_event_name`.
  - `UserPromptSubmit` adds `prompt`; `Stop` adds `last_assistant_message`; `SessionEnd` adds `reason`; `PreCompact` fires before compaction.
  - `SessionStart` (matchers `startup|resume|clear|compact`) can return `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"..."}}` and plain stdout also reaches the model. This is a native "resume" injection point.
  - Config shape: `{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"..."}]}]}}`.
- Continuous capture design: a `Stop` hook (and `UserPromptSubmit`, `PreCompact`, `SessionEnd`) runs `checkpoint capture --from-hook`, which reads `transcript_path` and incrementally syncs new lines into the working buffer. Re-reading the whole transcript and de-duplicating by message uuid is simpler and idempotent; JSONL transcripts are append-only.

## Capture: Codex CLI (second provider, later)

- Rollouts at `~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` (some newer builds compress to `.jsonl.zst`).
- Lines: `{"timestamp", "type", "payload"}`; `type` in `session_meta`, `response_item`, `event_msg`, `turn_context`.
  - `response_item` with `payload.type == "message"` has `payload.role` (`user`/`assistant`/`developer`) and `payload.content` blocks of `input_text` / `output_text`.
- Codex also has a hooks engine; not needed for the MVP.

## MCP

- Python SDK: `mcp` on PyPI (2.x current; 1.x FastMCP API `from mcp.server.fastmcp import FastMCP` with `@mcp.tool()` decorators, stdio transport). Keep the engine importable without `mcp` installed; the server is an optional extra.

## Landscape (what already exists)

| Tool | What it does | Gap relative to AI Checkpoint |
|---|---|---|
| Entire CLI (MIT, Thomas Dohmke) | Hooks into 8 coding agents; stores session transcripts as git refs `refs/entire/checkpoints/...` linked to code commits by trailer; `rewind`, `resume`, `explain`, `search` | Tied to code commits in a code repo; checkpoints are of the *code*, with the session attached. No structured "state" (decisions/open questions), no cross-provider resume prompt. |
| SpecStory | Auto-saves agent chats as markdown in `.specstory/history/`; `specstory resume` can reconstruct into another agent's native format | History log, not named checkpoints; no versioned state; cloud product. |
| continues (npm, ~1.2k stars) | Converts sessions across 16 agents into a prose handoff doc injected as the first message (10k-30k tokens) | One-shot handoff, no history/versioning, no structured state, no eval of handoff quality. |
| casr (Rust) | Canonical IR, bidirectional conversion that writes target agents' native session files | Conversion only; reverse-engineered formats break on updates. |
| ctx / ai-context-bridge, claude-remember, handover-mcp | Rate-limit handoff, persistent memory | Memory, not versioned checkpoints. |

Takeaways for scope:
1. Capture + transcript storage is a solved, crowded problem. The differentiator has to be the **checkpoint** itself: named, versioned, diffable, with a structured state section, and a resume context that measurably beats a summary.
2. Nobody publishes an eval of resume quality. The MVP doc's Test 4 (checkpoint vs summary) is the most defensible asset.
3. Coding-agent tools ignore web chats (ChatGPT/Claude.ai exports). Importers for the official export files are a cheap path to "any provider".

## MCP-based handoff tools (second pass, 2026-10-07)

| Tool | What it is | Overlap |
|---|---|---|
| Session Handoff MCP (Dev-Russo, TypeScript) | `memory_checkpoint` / `memory_resume`; structured snapshots (objective, done, decisions, pending) in `projects/<id>/checkpoints/`; optional git sync; Claude Code + Codex | Closest match to the MVP. Early stage (validation phase). Model-written state only, no raw transcript. |
| conversation-handoff-mcp (trust-delta) | `handoff_save/load/list/merge`; shared local HTTP server across Claude Desktop, Claude Code, Codex, Gemini CLI | In-memory clipboard; nothing persisted or versioned. |
| Memo MCP | `memo set` saves goals/tasks/decisions/files to Upstash Redis; restore by ID in another agent | Cloud, 24h TTL by default, no history. |
| OpenMemory MCP (Mem0) | Local shared memory layer across MCP clients | Long-term facts, not work checkpoints. |
| Letta Agent File (.af) | Open format for a whole agent: model config, message history, system prompt, memory blocks, tools | "Portable agent" definition; Letta-centric in practice. |
| Gemini / Claude imports (Mar 2026) | Gemini imports ChatGPT/Claude export ZIPs and memories; Claude imports memory via prompt | Platforms are adding one-way switching themselves. |

Implication: the MCP save/resume pattern with structured state exists already. Gaps nobody covers together: raw transcript + structured state in one checkpoint, git history with diff/branch, remote server for web chats, and published evidence that resume beats a summary.
