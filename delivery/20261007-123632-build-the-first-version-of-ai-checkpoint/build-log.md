## F-001 attempt 1
- What changed:
  - `.gitignore`, `pyproject.toml` (setuptools, src layout, requires-python >=3.10, no runtime deps; extras `mcp`, `anthropic`, `openai`, `dev`; pytest config with `pythonpath=src`), `README.md` (short stub).
  - `src/ai_checkpoint/errors.py`: `CheckpointError`, `ValidationError(field, message)`, `NotFoundError(ref)`, `StoreError`.
  - `src/ai_checkpoint/model.py`: dataclasses `Checkpoint`, `Decision`, `VerbatimItem`, `LastExchange`; `Checkpoint.from_dict` is the single validator (errors name the field, e.g. `verbatim[0].label`); `to_dict` emits every key; `INPUT_FIELDS`/`SECTION_FIELDS` constants for F-002's tool schema.
  - `src/ai_checkpoint/redact.py`: `redact_text`/`redact_obj` (sk-/sk-ant-, ghp_/github_pat_, AKIA/ASIA, AIza, xox*, PEM private keys, `Bearer x`, `api_key=`/`token=`/`password=`/`secret=` assignments incl. quoted and JSON `"password": "x"`). Replaces only the secret with `[REDACTED]`.
  - `src/ai_checkpoint/brief.py`: stub hook. `estimate_tokens` (ceil(chars/4)) and `render_brief(cp)` (plain placeholder rendering of all sections). F-002 should replace `render_brief` body keeping the signature `render_brief(cp: Checkpoint) -> str`; `GitStore.list` calls it via the module (so listings pick up the real brief, token counts included).
  - `src/ai_checkpoint/store.py`: `GitStore(root=None, clock=None)` with `save(dict|Checkpoint) -> SaveResult(checkpoint_id, commit, checkpoint)`, `resolve(ref) -> id`, `get(ref) -> Checkpoint`, `list(chat_name=None) -> Listing` (`.checkpoints` newest first, `.chats` grouped dict, `.to_dict()`), `path_for(id)`, `default_root()`.
  - `src/ai_checkpoint/__init__.py`: public exports (no mcp/anthropic/openai import).
  - `tests/conftest.py`, `tests/test_store.py`: 38 tests covering each acceptance criterion.
- How to run it: `pip install -e .[dev]` then `pytest`. Example: `AI_CHECKPOINT_HOME=/tmp/x python -c "from ai_checkpoint import GitStore; print(GitStore().save({...}))"`.
- Tests: `python3 -m pytest -q` -> 38 passed (offline, ~1s). `pip install -e .` succeeds.
- User-visible changes: None (new package). Console scripts (`ai-checkpoint`, `ai-checkpoint-mcp`, `checkpoint-eval`) are deliberately not declared yet because their modules do not exist; F-002/F-003 add them to `[project.scripts]`.
- Notes:
  - Stack: stdlib + system `git` via subprocess (no GitPython), src layout, setuptools.
  - Next id = max(files on disk, ids found in `git log --name-only`) + 1, so ids survive deleted files. Saves are serialised with an flock on `.git/ai-checkpoint.lock` (no-op without fcntl). Commits pass `-c user.name/user.email/commit.gpgsign=false --no-verify`, so no global git config is needed; GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE are stripped from git's env. If git fails after the file is written, the file is removed and unstaged.
  - Redaction runs before validation, on all string fields including names (so commit messages are clean); `resumed_from` is exempt and resolved raw. Heuristics to avoid code false positives: `token=get_token()`, `max_tokens=1000`, `token=$VAR`, `<placeholder>`, `None/true/false` and lowercase-word `Bearer authentication` are left alone. Best effort only.
  - Validation choices (spec silent): chat_name may not contain `/`; names may not contain control chars/newlines or look like `cp-NNN`; optional fields accept `null` as default; list items and decision/verbatim fields must be non-empty strings; unknown input keys are ignored; caller-supplied `checkpoint_id`/`created_at` are overwritten.
  - Ref resolution: id (`cp-7` is normalised to `cp-007`), then `chat/name`, then bare name (newest wins across chats), with a case-insensitive fallback if nothing matches exactly. Ordering is by id (not timestamp).
  - Corrupt/unreadable checkpoint files are skipped when listing/resolving rather than failing.
  - Deferred: delete/update (out of scope), real brief wording (F-002).

## F-002 attempt 1
- What changed:
  - `src/ai_checkpoint/brief.py`: real `render_brief` (deterministic, fixed section order `BRIEF_ORDER`, `EMPTY_MARK` for empty sections, verbatim/last exchange in fences longer than any backtick run, closing "confirm the current step" instruction); `fence_for`/`fenced` helpers.
  - `src/ai_checkpoint/server.py`: stdio MCP server (`create_server(store=None)`, `main`), tools save/list/get/resume + prompt `resume`; `save_checkpoint` description and per-field descriptions are the compaction instructions. Core errors become `ToolError` (isError over the wire).
  - `src/ai_checkpoint/cli.py`, `__main__.py`: `save --file`, `list [--chat]`, `get`, `resume`.
  - `pyproject.toml`: `[project.scripts]` `ai-checkpoint`, `ai-checkpoint-mcp`. `README.md`: install, mcpServers config, CLI, brief format.
  - `tests/test_server.py` (stdio subprocess session, schema, in-process errors), `tests/test_brief_cli.py` (brief, byte-exact fences, CLI).
- How to run it: `pip install -e .[mcp]`; `ai-checkpoint-mcp` or `python -m ai_checkpoint.server`; `ai-checkpoint list|get|resume|save`.
- Tests: `python3 -m pytest -q` -> 51 passed (~4s).
- User-visible changes: listing `brief_tokens` now reflects the real brief (larger than the F-001 placeholder). `get_checkpoint` adds `brief_chars` and `brief_tokens` to the checkpoint dict. CLI `get` prints JSON; `list` prints a grouped text table.
- Notes: installed `mcp` is 2.2.0 (FastMCP renamed `MCPServer`); server imports `mcp.server.mcpserver` and falls back to `mcp.server.fastmcp` for 1.x (1.x path untested). In-process test expects `ToolError` from `server.call_tool` (v2 behaviour); over stdio it is `isError`. Redaction still applies on save. Client label in the header is the stored `client` ("unknown" if unset).

## F-002 attempt 2
- What changed: `src/ai_checkpoint/cli.py` rejects non-object JSON (str, null, number, list, `[]`) with `error: <file|stdin> must contain a JSON object (got <type>)`, reports too-deeply-nested JSON cleanly, and has a last-resort handler for ValueError/TypeError/KeyError/RecursionError that prints `error:` instead of a traceback. `src/ai_checkpoint/store.py` `GitStore.save` raises ValidationError("checkpoint: must be an object (got X)") for non-mapping input instead of crashing in `dict(data)`. `tests/test_brief_cli.py`: new tests for non-object JSON (7 cases), deeply nested JSON, empty stdin, and store rejection of non-mappings.
- How to run it: `echo '[1]' | ai-checkpoint save --file -`
- Tests: `python3 -m pytest -q` gave 65 passed.
- User-visible changes: new error messages for non-object input; `save()` of a non-mapping now raises ValidationError, not TypeError/ValueError.
- Notes: Not done (outside the QA finding, noted only): resume prompt with unknown ref returns a generic SDK error; in-process tests assert ToolError rather than isError; `AI_CHECKPOINT_HOME` unusable path reports "no checkpoints"; `mcp>=1.2` fallback untested.

## F-002 attempt 3
- What changed: src/ai_checkpoint/store.py (GitStore.save normalises non-Checkpoint input via dict(); only TypeError/ValueError from that become ValidationError "checkpoint: must be an object"); tests/test_brief_cli.py (non-mapping test now uses b"ab" instead of []; new tests for list-of-pairs, duck-typed mapping, iterator, and [] giving "chat_name: is required"). CLI non-object JSON handling unchanged (still clean error, no traceback; covered by test_cli_save_non_object_json).
- How to run it: unchanged
- Tests: python3 -m pytest -q (full suite) - see result below
- User-visible changes: GitStore.save([]) reports "chat_name: is required" again (F-001 behaviour); otherwise none.
- Notes: none
