VERDICT: PASS

F-002 "Workspace section and 'set up first' checklist on resume", attempt 2. I checked the uncommitted working tree on top of HEAD ccd473d (F-001). Imports were confirmed through `__file__`: `~/mnt/ai-checkpoint/src/ai_checkpoint/__init__.py` for the new code, and `~/qa-wt3/src/...` / `~/qa-wt0/src/...` for the old code. Manual checks used throwaway stores under `$HOME/qa-f2b` with `AI_CHECKPOINT_HOME` (since deleted). `~/.ai-checkpoint` was not touched. Since attempt 1, the only source change is in `src/ai_checkpoint/redact.py`: a new `_URL_CRED` pattern and `_url_cred_sub`. `tests/test_workspace.py` gained 11 tests.

9 of 9 criteria met.

| Criterion | Result | Evidence |
|---|---|---|
| 1. Optional `workspace` covering every ROADMAP item 8 category; each item has status `still_relevant`/`done_with`; a fully populated workspace round-trips | met | `WORKSPACE_CATEGORIES` covers files (path), repos (path, branch, last_commit), access (path, permissions), connectors, tools, env_vars, skills and references (name, url). I built my own full workspace with every category, mixed statuses and two permissions. Result: `to_dict()["workspace"] == input` -> True, and `from_dict(to_dict()).to_dict() == to_dict()` -> True. |
| 2. Missing/null/partial workspace gives empty defaults; unknown status or missing path/name raises ValidationError naming the field | met | Absent, `None` and `{}` all load, with no `workspace` in `to_dict`. Partial `{"tools":[...]}` keeps only tools. Errors: `status:"maybe"` -> `workspace.repos[0].status`; missing path -> `workspace.files[0].path: is required`; `name:""` -> `workspace.connectors[0].name: must not be empty`; missing status -> `workspace.env_vars[0].status`; `permissions:"delete"` -> `workspace.access[0].permissions`; `url:5` -> `workspace.references[0].url`; a `None` item -> `workspace.tools[0]`; `workspace:"notadict"` -> `workspace`. |
| 3. `NAME=value` env var stored as `NAME` with no value in the saved file | met | `GitStore.save` with `ANTHROPIC_API_KEY=sk-ant-abc123def456`, `PG=postgres://u:pw9999xx@h/db` and `EMPTY=`. On disk the names are `ANTHROPIC_API_KEY`, `PG` and `EMPTY`, and neither `sk-ant-abc` nor `abc123def456` nor `pw9999xx` is in the file. Through MCP `save_checkpoint`, `X=sekretvalue1` is absent from both the file and the resumed brief. pytest `test_env_var_value_never_stored` passes. |
| 4. Secrets anywhere in workspace strings (tokens in URLs, `Bearer ...`, `password=...`) are redacted in the saved file | met (fixed since attempt 1) | Saved file through `GitStore.save`: repo path `https://user:[REDACTED]@git.example.com/r.git`; refs `postgres://admin:[REDACTED]@db.internal:5432/x`, `https://oauth2:[REDACTED]@gitlab.com/x` and `https://api.x.com/v1?access_token=[REDACTED]`; tool `curl -H 'Authorization: Bearer [REDACTED]'`; `mysql password=[REDACTED]`; note `api_key=[REDACTED] and token=[REDACTED]`. None of the 11 secret substrings I planted (`tok_abcdef123456`, `hunter2pw`, `glpat-`, `qwerty98765`, `eyJhbGci`, `Sup3rS3cret`, `AKIAABCD`, `abcd1234efgh`, `sk-ant-abc`, ...) appear in the file. Through MCP `save_checkpoint` with `https://bob:s3cr3tPAT99@git.example.com/r.git`, the file and the `resume_checkpoint` brief both show `bob:[REDACTED]@git.example.com`, and `s3cr3tPAT99` appears in neither. The new pytest cases (`test_url_credentials_redacted`, `test_url_credentials_in_workspace_redacted_on_disk`) pass. |
| 5. Brief shows a 'Set up first' checklist (before 'Before you continue') with only `still_relevant` items | met | "Set up first" is at index 1105 and "Before you continue" at 1737. The checklist lists folders (`~/mnt/agent-consultancy (permissions: delete, push)`), connectors, repo + branch + last commit (`~/mnt/ai-checkpoint (branch feat/x; last commit ccd473d F-001)`), tools, env var names, skills, files and references. The `done_with` items `old.txt`, `Slack` and `JIRA-12` are absent from the section. |
| 6. Brief tells the resumed AI to ask the user before requesting folder access or a connector | met | The brief contains "Ask the user before you request any folder access or connector; do not assume you already have it." pytest `test_brief_tells_ai_to_ask_before_access` passes. |
| 7. No workspace, or all `done_with`, gives no checklist | met | Neither case contains "Set up first". The all-`done_with` brief is byte-identical to the brief with no workspace (True). |
| 8. save_checkpoint description asks for `workspace`, a still-relevant/done-with judgement and env var names only; pinned hash and length in tests/test_eval.py updated with an explanatory comment; both hash tests pass | met | The description contains "Fill `workspace` ... Judge each item: mark it `still_relevant` ... `done_with` ... Give env var names only, never their values". The sha256 of `SAVE_DESCRIPTION` is `0b89d3ba57a21562...` and its length is 2279, which match the pins. The `git diff` of `tests/test_eval.py` shows the comment explaining why and giving the old values. `pytest test_save_description_matches_committed_head_text test_registered_save_tool_description_matches_head_hash` -> 2 passed. |
| 9. Old-format fixture still renders a byte-identical brief; `pytest -q` has 0 failures and the 117 previously passing tests are still present | met | `pytest -q` -> `173 passed in 30.92s`. Test IDs collected at 21c0624 in a worktree: 117. In the current tree: 173. Old IDs missing now: 0. I placed the fixture as cp-003 and ran CLI `resume cp-003` with the old code (HEAD worktree) and with the new code: `cmp` shows them identical, and both are identical to `tests/fixtures/old_format_brief.golden.md`, which is unchanged (`git diff --stat` empty). The old-fixture pytest tests pass (4). |

## Extra checks
- **Edge inputs for the new URL redaction** (`redact_text`, new code):
  - Placeholders are kept: `postgres://${USER}:${PASS}@h/db`, `https://u:<password>@h`, `https://u:%s@h`.
  - An empty password is kept: `https://user:@host`.
  - Case doesn't matter: `HTTPS://U:P4ss@H` -> `HTTPS://U:[REDACTED]@H`.
  - Quoted or backticked URLs and a URL followed by other text are handled.
  - `amqp://guest:guest@localhost:5672/` -> `guest:[REDACTED]@` (a default credential is redacted, which is harmless).
  - Idempotence holds. `https://x-access-token:ghp_...@github.com` is already caught by the token pattern, and the URL pass leaves `[REDACTED]` alone.
- **Known limitation (note, not a FAIL):** a raw `@` in the password redacts only up to that character. `https://user:p@ss@host/x` -> `https://user:[REDACTED]@ss@host/x`, which leaks the tail `ss`. The builder documented this. Such URLs are malformed (RFC 3986 requires `@` to be percent-encoded), so real tools would not produce them.
- **False positive (note):** `url=https://x.com:80@` -> `https://x.com:[REDACTED]@`. Strictly, that is RFC userinfo, so it is arguably correct. I found no realistic text affected.
- Notes from attempt 1 still stand and are unchanged by design:
  - `status` is required on every item, so one missing status rejects the whole save.
  - Unknown workspace categories are ignored.
  - An `export ` prefix stays in env var names.

## Regression sweep
**Code paths touched since HEAD:**
- `redact.redact_text` (new `_URL_CRED` pass, used by `redact_obj` -> `GitStore.save` for every field)
- `model.Checkpoint` workspace parsing/serialising
- `brief.render_brief` (`_setup_first`)
- `schema` description/field texts
- `server.save_checkpoint` Ws* models
- `tests/test_eval.py` pins

**Old vs new comparison:** HEAD worktree at `$HOME/qa-wt3`, with old imports confirmed via `__file__`.
- **`redact_text` on 48 hand-picked strings.** All of these were unchanged in both versions:
  - plain URLs: `https://example.com/t/1`, `http://localhost:8080/api`, `http://[::1]:8080/x`, `redis://localhost:6379/0`, `postgres://localhost:5432/db`, `https://host:443/x@y`, `https://a.com/@user`, `https://medium.com/@author/post`, `file:///Users/me/x@y`, `s3://bucket/key:v@1`, `jdbc:mysql://host:3306/db?user=a`, `see https://x.com/a:b@c`
  - git and ssh remotes: `git@github.com:o/r.git`, `ssh://git@github.com/o/r.git`, `ssh://git@github.com:22/o/r.git`, `https://user@host/x`
  - emails and mailto: `mailto:alice@example.com`, `alice@example.com`
  - other text with `@` or `:`: `user@host:/path`, `scp user@host:file .`, `Time 10:30 @ office`, `ratio 3:2 @home`, `A:B@C`, `prose: hi@there`, `C:\Users\me`, `${DB_URL}`, and the empty string

  The only differences were `scheme://user:PASSWORD@host` strings, where the password became `[REDACTED]`. Those changes are what criterion 4 requires.
- **`redact_text` on every .py/.md/.json/.toml/.txt/.sh file in the repo** (36 files, excluding `.git`/`delivery`): old and new output are identical (0 diffs).
- **`to_dict()` JSON + `render_brief()` hashed for 9 inputs:** identical for all of them. Inputs:
  - VALID
  - the old-format fixture
  - required fields only
  - decisions with `rejected`
  - unicode and multi-line notes containing a URL
  - `workspace: null`
  - `workspace: {}`
  - an unknown top-level key
  - a context full of emails, git remotes and `@`/`:` text
- **On-disk JSON from `GitStore.save`** of that last input (minus `created_at`): identical.
- **CLI resume of the old fixture:** byte-identical between the old and new code.

No regressions found. Worktrees `$HOME/qa-wt3` (HEAD) and `$HOME/qa-wt0` (21c0624) were removed, and `git worktree list` shows only the main tree. Scratch directory `$HOME/qa-f2b` was removed.
