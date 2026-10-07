
## F-001 attempt 1
- What changed: src/ai_checkpoint/store.py (msvcrt.locking path on fixed 1-byte range at offset 0 with retry + unlock in finally, no-op only without both modules; git calls pass core.autocrlf=false/safecrlf=false, errors="replace"; local autocrlf=false on init); src/ai_checkpoint/cli.py (reconfigure stdin/stdout/stderr to UTF-8); tests/test_windows_sim.py (13 new Windows-simulation tests); README.md (Windows notes: checks simulate Windows on Linux, real-Windows verification by testers).
- How to run it: python -m pytest -q
- Tests: `python -m pytest -q` -> 130 passed (117 existing + 13 new). schema.py untouched.
- User-visible changes: Lock wait on Windows times out with StoreError after 60 s; CLI output is always UTF-8; git commands ignore user autocrlf.
- Notes: Ref parsing and default_root already pathlib/platform-independent (tests added only). Lock file open() has no encoding (empty file, never read). Missing-mcp friendly message belongs to F-002, not done. Not committed.

## F-001 attempt 2
- What changed: src/ai_checkpoint/cli.py `_force_utf8` now skips streams already UTF-8 and otherwise reconfigures with `errors=stream.errors`, preserving each stream's error handler (fixes stderr backslashreplace regression). tests/test_windows_sim.py: regression test running CLI with a non-UTF-8 `--file` argument.
- How to run it: `python -m pytest -q`
- Tests: see result below
- User-visible changes: None (restores HEAD behaviour for error messages with undecodable argv).
- Notes: optional QA items (`__main__` block, msvcrt retry sleep) not done; out of scope.

## F-001 attempt 3
- What changed: src/ai_checkpoint/cli.py: `_force_utf8()` now only touches stdout/stderr (stdin untouched, so input decoding is as at HEAD); each stream keeps its original error handler. src/ai_checkpoint/store.py: msvcrt lock retry loop now sleeps `_LOCK_RETRY_SLEEP_S` (0.05 s) between retries; it previously busy-waited when locking raised OSError. tests/test_windows_sim.py: added `test_cli_stdin_not_reencoded_under_cp1252` (cp1252 bytes via `save --file -` under PYTHONIOENCODING=cp1252, rc=0 and name stored as café) and `test_msvcrt_retry_sleeps_between_attempts`.
- How to run it: `python -m pytest -q`
- Tests: `python -m pytest -q` -> 133 passed
- User-visible changes: stdin/--file decoding is back to HEAD behaviour (no longer forced to UTF-8). The msvcrt retry sleep is not visible apart from lower CPU use while waiting for the lock.
- Notes: Deferred, not done: a `__main__` block in cli.py (QA criterion 13 note), and chaining the last OSError as the cause of the lock timeout. I briefly ran `git stash` by mistake, which reverted the working tree. I restored it with `git stash pop`, and the final full-suite result above was taken before that. I am re-running the suite once more now.
