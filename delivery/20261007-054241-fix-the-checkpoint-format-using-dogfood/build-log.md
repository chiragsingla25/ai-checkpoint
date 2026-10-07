
## F-001 attempt 1
- What changed:
  - `src/ai_checkpoint/model.py`: new `Rejected` dataclass, `Decision.rejected`, `HOW_FAR_VALUES`, `_rejected` validator (errors name `decisions[i].rejected[j].option|how_far|note`, `decisions[i].rejected`); `to_dict` writes `rejected` only when non-empty (keeps old shape and the existing store test).
  - `src/ai_checkpoint/brief.py`: decisions render `  Rejected: <option> (<discussed|prototyped|built, then removed>) - <note>` under their decision; decisions without rejected render exactly as before.
  - `src/ai_checkpoint/schema.py`: field descriptions for `decisions`, `decisions.rejected(.option/.how_far/.note)`, and the compaction field type text. `SAVE_INSTRUCTIONS`/`SAVE_DESCRIPTION` deliberately untouched so the pinned hash stays valid (F-002 owns that change).
  - `src/ai_checkpoint/server.py`: `RejectedIn` model (how_far as Literal enum) and `DecisionIn.rejected`.
  - `tests/test_rejected.py` (new, 21 tests), `tests/fixtures/old_format_cp.json` and `tests/fixtures/old_format_brief.golden.md` (golden rendered from the code before any edit).
- How to run it: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q`
- Tests: full suite 138 passed (117 existing + 21 new), 0 failed.
- User-visible changes: save_checkpoint tool input schema gains `decisions[].rejected` and the `decisions` field description is longer (the tool description text itself is unchanged); the compaction prompt for the eval kit lists the new field; briefs show `Rejected:` lines only when rejected items exist; stored JSON includes `rejected` only when non-empty.
- Notes: old-format fixture is read from a hand-placed `cp-003.json` (store resolves path by file name, so the fixture's id and filename match). Golden brief is exercised via Store.get, MCP resume_checkpoint (in-process) and CLI. Multi-line option/note text is collapsed to single-spaced in the brief. Workspace section not touched (F-002).

## F-002 attempt 1
- What changed:
  - `src/ai_checkpoint/model.py`: optional `workspace` (categories files, repos, access, connectors, tools, env_vars, skills, references; each item needs its key field path/name plus `status` of still_relevant|done_with; extras: note, branch, last_commit, permissions, url). Errors name e.g. `workspace.repos[0].status`. Env var `NAME=value` is reduced to `NAME`. `to_dict` omits `workspace` when empty (old shape kept) and omits empty categories.
  - `src/ai_checkpoint/brief.py`: "Set up first" section (after Notes, before "Before you continue") built only from still_relevant items; starts with "Ask the user before you request any folder access or connector; do not assume you already have it." Absent when no still-relevant items.
  - `src/ai_checkpoint/schema.py`: SAVE_INSTRUCTIONS gained a `rejected` bullet and a `workspace` bullet (judge still_relevant/done_with, env var NAMES only, no credential paths); field descriptions for `workspace` and each category; compaction field list.
  - `src/ai_checkpoint/server.py`: pydantic models for workspace on `save_checkpoint` (status as Literal enum).
  - `tests/test_eval.py`: pinned sha256/length updated deliberately, with a comment explaining why.
  - `tests/test_workspace.py` (new, 24 tests incl. parametrized).
- How to run it: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q`
- Tests: 162 passed, 0 failed (138 previous incl. both hash tests + the F-001 old-format golden brief tests, unchanged and passing, + 24 new).
- User-visible changes: save_checkpoint tool description text is longer (two new bullets) and its input schema gains `workspace`; resumed briefs show a "Set up first" section only when still-relevant workspace items exist; stored JSON gains `workspace` only when non-empty; env var values are dropped silently; `status` is required on every item (missing status is a ValidationError).
- Notes: access items use `path` for the folder. Unknown keys inside items (e.g. a `value` on an env var) are ignored and never stored. No resume-time existence checks (out of scope). Checklist items from different categories are grouped one line per category.

## F-002 attempt 2
- What changed:
  - `src/ai_checkpoint/redact.py`: new `_URL_CRED` pattern; the password/token in `scheme://user:SECRET@host` is replaced with `[REDACTED]`, host and path stay readable (`https://user:[REDACTED]@git.example.com/r.git`). Placeholders (`${VAR}`, `<x>`) and URLs without a password are left alone. Applies to every saved field since redaction is shared.
  - `tests/test_workspace.py`: added tests for the four reported URLs, idempotence, no-credential URLs unchanged (`https://example.com/t/1`, `git@github.com:o/r.git`, etc.), and an on-disk check through GitStore.save.
- How to run it: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q`
- Tests: 173 passed, 0 failed (162 previous incl. redaction tests and old-format golden brief + 11 new).
- User-visible changes: passwords in URLs like `scheme://user:pw@host` are now saved as `[REDACTED]` in any field (notes, verbatim, workspace).
- Notes: a password containing a literal unencoded `/` or `@` is only redacted up to that character. QA's other notes (required status, `export` prefix in env var names) not changed.
