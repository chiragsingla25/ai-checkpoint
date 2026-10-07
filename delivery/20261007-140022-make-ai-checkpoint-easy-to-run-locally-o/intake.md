# Intake

## Understanding
Make AI Checkpoint easy to run on the user's Mac. (1) Strengthen the MCP server-level `instructions` so clients call save_checkpoint / resume_checkpoint when the user asks to checkpoint or resume (a real Claude Code session searched git/files for "resume trial/test-v1" instead), explain how to pick chat_name/checkpoint_name, and on resume read the brief and confirm the current step. (2) Add `scripts/setup-mac.sh`: one command that builds a repo-local `.venv`, installs `.[mcp]`, registers the server for Claude Code (user scope) and Claude Desktop with the venv's absolute `ai-checkpoint-mcp` path, then prints next steps; plus a README quick start.

## Size
small: a text change to one constant plus one shell script and a README section; no core logic changes.

## Existing project
Python package (`src/ai_checkpoint`, requires-python >=3.10, setuptools, extras `mcp`, `dev`), console scripts `ai-checkpoint`, `ai-checkpoint-mcp`, `checkpoint-eval`. `server.py` already passes a short `SERVER_INSTRUCTIONS` to FastMCP; it needs expanding. `SAVE_DESCRIPTION` lives in `schema.py` and is pinned by tests. No `scripts/` dir yet. Tests: `pytest` from repo root (110 tests; stdio session tests in tests/test_server.py). Sandbox has Python 3.13 and `mcp` installed; no `claude` CLI, not macOS.

## Recommended stages
build, qa. Both features are straightforward; QA must exercise the script in a Linux sandbox with a temp HOME, a stub `claude` that logs argv, and `--desktop-config` pointing at a temp file.

## Assumptions
- `AI_CHECKPOINT_HOME` written by the script is `$HOME/.ai-checkpoint` expanded to an absolute path at run time (the request's `/root/.ai-checkpoint` is that expansion in the requester's shell).
- Config-path override is a `--desktop-config PATH` flag; default is `~/Library/Application Support/Claude/claude_desktop_config.json`. Interpreter defaults to `python3` on PATH (pyenv shim), overridable with `PYTHON=...`, which also makes the <3.10 failure testable.
- Claude Code registration: `claude mcp remove ai-checkpoint -s local` and `-s user` (errors ignored), then `claude mcp add -s user ai-checkpoint -e AI_CHECKPOINT_HOME=... -- <abs venv path>`. Remove-then-add is the idempotency mechanism.
- JSON editing of the Desktop config is done with the venv's (or chosen) Python, not jq, so no extra dependency. Backup is a timestamped copy alongside the file, made only when the file exists and will change or be rewritten.
- The script resolves the repo root from its own location, so it works from any cwd within reason; it does not need macOS to run (only the default path is Mac-specific).
- Instructions stay within the server's `instructions`; tool descriptions other than possibly minor docstrings are not changed, and `SAVE_DESCRIPTION` is untouched.

## Open questions
