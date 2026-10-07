# Intake

## Understanding
Build the AI Checkpoint MVP: a local-first Python tool (stdlib engine) that captures Claude Code conversations from their JSONL transcripts into a provider-independent conversation format, keeps that working buffer current through Claude Code hooks, saves named checkpoints as JSON under `.ai-checkpoint/` with one git commit each, and generates a resume context that can be pasted into a new conversation or injected via a SessionStart hook. A `checkpoint` CLI (init, capture, save, list, show, resume) is the main interface; an optional MCP server exposes save/list/get/resume. Obvious secrets are redacted before anything is written or committed.

## Size
large: a new multi-module package (models, capture adapter, hook integration, storage + git, resume, CLI, optional MCP) across MVP phases 1-5, built from an empty project.

## Existing project
Empty apart from `docs/MVP.md` (spec) and `docs/research.md` (Claude Code transcript/hook format, MCP SDK notes). No code, no pyproject, no tests, not a git repo. Test command to be established: `python -m pytest -q`. No real Claude Code install in the sandbox, so capture is verified against fixture JSONL transcripts built to match docs/research.md.

## Recommended stages
build, qa. The spec and research already fix the design closely enough that no separate design/research stage is needed; QA is needed because Test 1/Test 2 and the git/secret criteria are easy to get subtly wrong.

## Assumptions
- Package name `ai_checkpoint` (src layout), console script `checkpoint`, also `python -m ai_checkpoint`. Python 3.10+. `mcp` only as an optional extra.
- Store lives at `<root>/.ai-checkpoint` with root defaulting to cwd, overridable by `--root` / `AI_CHECKPOINT_ROOT`. The `.ai-checkpoint` folder is its own git repo, separate from any project repo.
- Universal message roles: `user` (human-typed), `assistant`, and `tool` for tool results; `tool_use` blocks kept as structured data on the assistant message; `thinking` blocks dropped. Split assistant lines sharing `message.id` merge into one message. Message dedup key: source uuid / message.id.
- `state/current.json` points at the most recently captured conversation; `save` checkpoints that conversation (a `--conversation ID` override is acceptable).
- Checkpoint `messages` is a full snapshot of the conversation at save time (raw messages are the source of truth). `state.objective` defaults to the first human prompt; other state lists are empty unless given via `save --objective/--next-step`. No LLM extraction.
- Checkpoint IDs are sequential `cp-NNN` per store.
- Redaction is regex-based for common credential shapes (sk-ant-, sk-, ghp_/gho_/github_pat_, AKIA, xox*, Bearer tokens, `password=`/`api_key=` style assignments); false negatives on unusual secrets are accepted for the MVP.
- SessionStart injection uses a "pending resume" set by `checkpoint resume <id> --on-next-start`, consumed by the next SessionStart hook call. `checkpoint install-hooks` is added (not in section 30) because continuous capture is in scope and needs a way to register hooks.
- Hook commands must never fail the host agent: they exit 0 on bad input.

## Open questions
None blocking. (Whether SessionStart should auto-inject the latest checkpoint without an explicit `--on-next-start` is a product choice; the explicit opt-in was assumed to avoid surprising context injection.)
