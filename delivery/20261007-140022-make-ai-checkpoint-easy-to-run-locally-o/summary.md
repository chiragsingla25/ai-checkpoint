# Run summary: 20261007-140022-make-ai-checkpoint-easy-to-run-locally-o

Request: make AI Checkpoint easy to run locally on the user's Mac (server instructions so clients route checkpoint/resume requests to the tools; one-command setup script). Plan: intake -> build -> qa.

| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 MCP server instructions | 1 | PASS (6/6) | e023081 |
| F-002 scripts/setup-mac.sh + README quick start | 1 | PASS (12/12) | see git log |

User-visible changes: MCP `initialize` now returns server instructions; new `scripts/setup-mac.sh` (creates .venv, installs .[mcp], registers with Claude Code at user scope, merges into Claude Desktop config with a backup; --dry-run, --desktop-config).

Known gaps: script not executed on a real Mac or real bash 3.2 (static review only); if `claude mcp add` fails the Desktop step is skipped; a stale .venv built with an old Python surfaces as a pip error rather than a tailored message.
