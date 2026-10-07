
## F-001 attempt 1
- What changed: src/ai_checkpoint/server.py (SERVER_INSTRUCTIONS expanded: routing, bare-ref resume, naming, confirm step, list_checkpoints; already passed to both MCPServer and FastMCP fallback via `_Server(..., instructions=)`); tests/test_server.py (new initialize-instructions test, also checks save description equals SAVE_DESCRIPTION)
- How to run it: python -m ai_checkpoint.server
- Tests: `python -m pytest -q`
- User-visible changes: the `instructions` string returned at MCP initialize is longer and more directive.
- Notes: schema.py untouched.

## F-002 attempt 1
- What changed: scripts/setup-mac.sh (new, executable; venv + `pip install -e .[mcp]`, Claude Code user-scope registration after removing local and user entries, Desktop config merge with backup via Python stdlib, `--dry-run`, `--desktop-config`, Python >=3.10 check, malformed-config preflight, next steps); tests/test_setup_script.py (new; runs the script on a repo copy with temp HOME, stub `claude`, stub old python); README.md (Quick start (macOS) section before Install)
- How to run it: `./scripts/setup-mac.sh [--dry-run] [--desktop-config PATH]`; `PYTHON=/path/to/python3.12` to pick the interpreter
- Tests: `python -m pytest -q` -> 117 passed (new file takes ~13s because it pip-installs into a temp venv; needs a pip index). Script run under `bash -euo pipefail`. Not run on a real Mac or bash 3.2; avoided arrays, `mapfile`, `${var,,}` and GNU-only flags.
- User-visible changes: None beyond the new script and README section.
- Notes: .venv was already in .gitignore. Install is editable (`-e`). Desktop config is validated before the venv is created, so a bad file stops the script with nothing changed. No backup or rewrite when the entry is already identical. Backups are named `<config>.bak-YYYYmmddHHMMSS`. `claude mcp add` failure aborts with an error; `remove` failures are ignored. Python version is read with `-c`, falling back to `--version`.
