# Roadmap: future enhancements

Everything researched or designed so far that is **not** in the first build. Sources and competitor details are in `research.md`; the original long-term design is in `MVP.md`.

Order is a suggestion. Run the handover evaluation first: if checkpoints do not beat a plain summary, revisit the format before building more.

## 1. Online version for Claude.ai and ChatGPT on the web
- Run the same MCP server over HTTPS (streamable HTTP transport) so web clients can add it as a custom connector. Web clients cannot reach a local process.
- **GitHub storage backend:** write `checkpoints/cp-NNN.json` to the user's private repo as one commit per save via the GitHub API. Same layout as the local git store, behind the same storage interface.
- Auth: GitHub OAuth per user, repo scoped to checkpoints only; never store tokens in checkpoint files (MVP section 27).
- Check current plan requirements for custom connectors on Claude.ai and ChatGPT (developer mode for write tools) before building.
- Zero-backend experiment first: GitHub's own remote MCP server + an instruction prompt that writes checkpoint JSON to a repo.

## 2. Raw transcript capture (MVP doc phases 1, 3)
- **Claude Code:** read `~/.claude/projects/<slug>/<session>.jsonl` at save time and attach the exact raw history to the checkpoint. Find the current session by project folder + most recently modified file, confirmed by a quote of the last user message. Handle split assistant lines (shared `message.id`), `tool_use`/`tool_result`/`thinking` blocks, unknown line types. Redact API keys/tokens before writing.
- **Codex CLI:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl[.zst]`, `response_item` messages.
- MVP Test 1 (50-message exact reconstruction) and Test 2 (multiple checkpoints, earlier ones unchanged) apply here.
- Optional Claude Code **plugin** bundling the MCP server + hooks (Stop/UserPromptSubmit for continuous capture, SessionStart to auto-inject an armed resume). One install; hooks stay optional.

## 3. Import from provider exports
- Importers for ChatGPT's `conversations.json` export and Claude.ai's export ZIP, producing checkpoints from old chats. Gemini already imports these files one-way; nobody turns them into restore points.

## 4. Version history features
- `diff` between two checkpoints (what decisions/steps changed).
- Branch tree view from `resumed_from`.
- Search across checkpoints.
- Artifact support (MVP phase 6): store code/files alongside a checkpoint.

## 5. Format interoperability
- Export a checkpoint as a Letta Agent File (`.af`) message history / memory blocks, and as a plain handover markdown for tools without MCP.
- Universal conversation format from MVP section 9 for raw history.

## 6. Smarter compaction
- Old history compressed, recent history raw, decisions structured, artifacts separate (MVP Test 5 ideas).
- Token budget per section; warn when `verbatim` is too large.
- Measure with the evaluation kit at 50 / 100 / 200 / 500 messages.

## 7. Evaluation as a publishable result
- Cross-provider runs: save in Claude, resume in ChatGPT and vice versa (MVP Test 7).
- Compare against existing tools' handover styles (Thredly-style summary, ChatGPT branch = full history, /handoff skill format).
- Write-up: method, rubric, results, failure modes.
