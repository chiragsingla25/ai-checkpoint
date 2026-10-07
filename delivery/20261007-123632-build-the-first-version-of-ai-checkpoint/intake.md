# Intake

## Understanding
Build the first version of AI Checkpoint per `docs/IDEA.md` "First build scope": a structured checkpoint format with validation, stored as JSON in a local git repo (one commit per save); a local stdio MCP server (save/list/get/resume tools plus a `resume` prompt) with a thin CLI; and an evaluation kit that measures handover quality of checkpoint brief vs plain summary vs full history, offline with a fake model and with real Anthropic/OpenAI models when keys are set. Everything in `docs/ROADMAP.md` (web/HTTP transport, GitHub backend, transcript capture, importers, diff/branch view, interop exports, smarter compaction) is out of scope.

## Size
large: a new Python package from scratch with three shippable parts (storage engine with git, MCP server + CLI, model-driven evaluation harness), each with its own tests.

## Existing project
Docs only: `docs/IDEA.md` (spec), `ROADMAP.md` (out of scope), `MVP.md` (older vision, not the spec), `research.md`. The project directory is a git repo with docs commits; no code, no tests yet. Sandbox has Python 3.13 and `mcp` installed. Tests to be run with `pytest` from the repo root. An earlier superseded run under `delivery/` is ignored.

## Recommended stages
build, qa. The user already agreed the three-part split, so no design/research stage is needed; QA must exercise the MCP server over real stdio and the git store in a temp dir.

## Assumptions
- Package name `ai_checkpoint`, `src/` or flat layout at the builder's choice, `pyproject.toml` with console scripts `ai-checkpoint`, `ai-checkpoint-mcp`, `checkpoint-eval`; `mcp`, `anthropic`, `openai` as optional extras, core engine stdlib-only (per research.md).
- Store layout: `<root>/checkpoints/cp-NNN.json` plus a git repo at `<root>`; the next id is derived from the git history/highest id ever committed so ids are never reused even if files are deleted. Commits set a local author identity so they work without global git config.
- Saved checkpoints are immutable; there is no delete or update tool in this version.
- A bare checkpoint_name that exists in several chats resolves to the newest one (rather than an ambiguity error).
- Token estimate is a heuristic (chars/4); no tokenizer dependency.
- Redaction is pattern-based and best effort; it applies to all text fields, including verbatim.
- `client` is free text (e.g. claude.ai, chatgpt, claude-code), defaulting to "unknown".
- The FakeModel produces plausible deterministic outputs (e.g. a compaction derived from the scenario's messages, answers by keyword matching over the handover text) so the pipeline and scoring are exercised end to end; its scores are not meaningful results.

## Open questions
None.
