VERDICT: PASS

F-001 attempt 3. Both earlier regressions are fixed:
- Attempt 1: stderr lost its error handler, so an undecodable `--file` argument printed `lost sys.stderr`.
- Attempt 2: stdin was forced to UTF-8, so a cp1252 `save --file -` now failed.

All 15 acceptance criteria are met as written. The sweep against HEAD found no input that worked before and fails now.

Scope note: these checks simulate Windows on Linux. They use a hidden `fcntl`, a fake `msvcrt`, CRLF files, an autocrlf git config and a cp1252 console via PYTHONIOENCODING. No real Windows machine was used. The testers do the real-Windows verification.

**Working tree after the builder's accidental stash/pop.** `git stash list` is empty (0 lines). `git status` shows README.md, src/ai_checkpoint/cli.py and src/ai_checkpoint/store.py as modified, and tests/test_windows_sim.py as untracked. `git diff HEAD --stat` gives 3 files, +66/-6. The diff contains every F-001 change from attempts 1–3:
- the msvcrt lock path with the new retry sleep
- `_GIT_CRLF` and `errors="replace"` in `_git`
- local `core.autocrlf=false` on init
- `_force_utf8` limited to stdout/stderr
- the README Windows notes

The test file has 16 tests, including both attempt-3 additions. HEAD is still `3e7d071`. Nothing was lost.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | pytest passes: 117 pre-existing tests plus the new Windows-simulation tests | met | `python -m pytest -q` gave `133 passed in 31.38s`. `python -m pytest -q --deselect tests/test_windows_sim.py` gave `117 passed, 16 deselected`. `tests/test_windows_sim.py -rA` gave 16 PASSED, including `test_cli_stdin_not_reencoded_under_cp1252` and `test_msvcrt_retry_sleeps_between_attempts`. |
| 2 | SAVE_DESCRIPTION unchanged; test asserts byte equality | met | `git diff HEAD --stat -- src/ai_checkpoint/schema.py src/ai_checkpoint/server.py` is empty. tests/test_server.py:129-131 asserts `save.description == SAVE_DESCRIPTION`. The MCP `list_tools()` descriptions and schemas are identical to HEAD (API sweep below). |
| 3 | `_lock` uses fcntl, then msvcrt, then a no-op; msvcrt locks a fixed range from offset 0, retries, and unlocks the same range in `finally` | met | From `git diff HEAD -- src/ai_checkpoint/store.py`: fcntl is tried first, and msvcrt is imported only if fcntl is None. The lock yields as a no-op only if both are None. The msvcrt loop does `fh.seek(0)` and then `msvcrt.locking(fd, LK_LOCK, _LOCK_BYTES=1)`. On OSError it retries with `time.sleep(0.05)` until a 60 s deadline, then raises StoreError. `finally` does `fh.seek(0)` and then `locking(fd, LK_UNLCK, 1)`. |
| 4 | A fake msvcrt records LK_LOCK then LK_UNLCK on the same fd and range, and the checkpoint is written and committed | met | `test_msvcrt_lock_used_and_unlocked` passes. It asserts the modes, fd, nbytes and seek position 0, that the file exists, and that there is 1 commit. |
| 5 | A failure inside the lock still calls LK_UNLCK and leaves no file | met | `test_msvcrt_unlock_on_failure` passes. A commit failure is injected, LK_UNLCK is the last call, and no `cp-*.json` is left. |
| 6 | With fcntl and msvcrt both hidden, save/list/get/resume work | met | `test_no_lock_modules_noop` passes. |
| 7 | Concurrent saves on Linux through fcntl get distinct sequential ids | met | `test_fcntl_concurrent_saves_distinct_ids` (5 threads, cp-001 to cp-005) passes, and so does the existing concurrency test. |
| 8 | UTF-8 + `\n` write, UTF-8 read; non-ASCII text round-trips with no `\r\n` | met | store.py:251 has `open(path, "x", encoding="utf-8", newline="\n")` and store.py:268 has `read_text(encoding="utf-8")`. `test_utf8_no_crlf_roundtrip` passes. In the fixed-clock API sweep, the checkpoint containing `café ✓ 日本\r\nx` has the same sha256 as on HEAD. |
| 9 | A CRLF file still loads in list/get/resume | met | `test_crlf_file_still_loads` passes. |
| 10 | Every git call uses encoding='utf-8' with safe errors; global autocrlf=true + safecrlf=true still works | met | There is a single `subprocess.run` in `_git` (store.py:131-134), with `encoding="utf-8", errors="replace"` and `-c core.autocrlf=false -c core.safecrlf=false`. I wrote a gitconfig with `autocrlf = true` and `safecrlf = true`, then ran `GIT_CONFIG_GLOBAL=gc AI_CHECKPOINT_HOME=<new> python -m ai_checkpoint save --file uni.json`. It returned rc=0 and `cp-001`, with a commit hash. `list` then shows `trial cp-001 uni`. `test_autocrlf_global_config_ignored` passes. |
| 11 | pathlib paths; default_root; no POSIX separators in filesystem paths | met | `test_default_root` passes. I grepped store/server/cli for `/` literals. The only hits are the git pathspec `f"{CHECKPOINT_DIR}/{id}.json"` (used only in git args), `refs/heads/main`, ref splitting, the commit message, and docstrings and descriptions. The filesystem path is `self.path_for(...)`, and the lock file is `self.root / ".git" / "ai-checkpoint.lock"`. |
| 12 | A backslash ref is a plain name; `chat/name` still resolves | met | `test_backslash_ref_is_plain_name` passes. In the API sweep, `get('chat\\name')` gives `NotFoundError: checkpoint not found: 'chat\\name'`, identical to HEAD. `trial/uni` and `TRIAL/UNI` resolve as on HEAD. |
| 13 | `PYTHONIOENCODING=cp1252 python -m ai_checkpoint.cli get/resume <ref>` exits 0 with no UnicodeEncodeError | met (as written; see note) | Run literally, the command gives `rc=0 out=0 err=` for both get and resume. cli.py has no `__main__` block, so it is a silent no-op. The meaningful form is `PYTHONIOENCODING=cp1252 python -m ai_checkpoint get trial/uni`, on a checkpoint containing `café ✓ 日本 €`. get gives rc=0, 511 bytes, with 日本 present. resume gives rc=0, 1070 bytes, with 日本 present. HEAD gives rc=1 for both under cp1252/ascii/latin-1 (sweep rows "get uni" and "resume uni"). `test_cli_utf8_under_cp1252[get/resume]` passes. |
| 14 | When git is missing: StoreError naming git; the MCP save_checkpoint tool returns a tool error; covered by a test with PATH set to an empty dir | met | `PATH=<empty dir> python3 -m ai_checkpoint save --file uni.json` gives `error: the 'git' executable was not found on PATH` with rc=1. `test_git_missing_is_store_error` and `test_git_missing_mcp_tool_error` pass. server.py is unchanged from HEAD. |
| 15 | The intake/QA notes and README say the checks simulate Windows on Linux and that the testers do real-Windows verification | met | README.md:67-69 "## Windows notes" says this. intake.md:18 says it. This file says it at the top. |

## Extra checks
- **Attempt-2 regression (stdin) is fixed.** The fixture is a valid checkpoint with `checkpoint_name: café` and `context: naïve €`, encoded as cp1252 bytes. Running `PYTHONIOENCODING=cp1252 python -m ai_checkpoint save --file - < cp1252.json` now gives rc=0 and `cp-004`. Its sweep output and stored file are byte-identical to HEAD under cp1252, cp1252:strict and latin-1, in both C.UTF-8 and C locales.
- **The stdin regression test guards a real failure.** I copied src and tests to scratch and added `sys.stdin` back into the `_force_utf8` tuple (the attempt-2 behaviour). `test_cli_stdin_not_reencoded_under_cp1252` then FAILED. It passes on the real tree.
- **Attempt-1 regression (stderr) is still fixed.** `save --file $'\xff.json'` prints `error: cannot read \udcff.json: [Errno 2] No such file or directory: '\udcff.json'` with rc=1. That output is identical to HEAD in all 12 encoding × locale combinations of the sweep.
- **Retry sleep.** `test_msvcrt_retry_sleeps_between_attempts` passes, with two OSErrors leading to two sleeps of more than 0. Carried-over note, not a failure: a non-contention OSError such as EBADF still retries for 60 s and is then reported as "timed out". The original error is not chained.
- **Criterion 13 wording** (carried over): `python -m ai_checkpoint.cli` is a no-op. Adding `if __name__ == "__main__": raise SystemExit(main())` to cli.py would make the documented command meaningful. The builder deferred this. It is optional.
- **Unchanged behaviour, recorded for the owner.** On a cp1252 console, UTF-8 bytes piped to `save --file -` are stored as mojibake (`cafÃ©`). This happens on HEAD and in the new code alike, and the stored files are identical. It is not a regression, and no criterion covers input decoding.

## Regression sweep
Code paths touched since HEAD:
- `GitStore._git`: `-c core.autocrlf=false -c core.safecrlf=false`, `errors="replace"`
- `GitStore._ensure_repo`: sets local `core.autocrlf=false`
- `GitStore._lock`: fcntl / msvcrt / no-op, with the retry sleep
- `cli._force_utf8` / `cli.main`: stdout and stderr only, skipped if already UTF-8, keeping each stream's `errors`

HEAD was checked out with `git worktree add <scratchpad>/qa3/old HEAD`. The same scripts were run with `PYTHONPATH` set to each `src`. The worktree was removed afterwards (`git worktree list` now shows only main), and the scratch directory was deleted.

1. **CLI matrix: 264 command blocks per version.** Six PYTHONIOENCODING settings (unset, utf-8, cp1252, ascii, latin-1, cp1252:strict) × two locales (C.UTF-8, C) × 22 commands:
   - Saves: from a Unicode file with CRLF and a tab, from a plain ASCII file, plain via stdin, cp1252 bytes via stdin, UTF-8 bytes via stdin, invalid JSON, an empty file, empty stdin, a missing file, and `$'\xff.json'`.
   - Reads: `list`, `get`/`resume trial/uni`, `get forecasting/v1`, `get cp-002`, `get café`, `get missing`, `get ''`, `get $'\xff'`, and `get 'chat\name'`.
   - Also `--help` and no arguments.

   I compared rc, stdout and stderr after normalising hashes, timestamps and the home path.
   - 234 of the 264 blocks are identical. These include every block under unset/utf-8, every save, every error path, and both earlier regression inputs.
   - 30 blocks differ, all under non-UTF-8 PYTHONIOENCODING:
     - 22 are `get uni`/`resume uni`. HEAD gives rc=1 with UnicodeEncodeError; the new code gives rc=0.
     - 8 are `list`/`get café`. Both versions give the same rc. HEAD writes in the console encoding (`caf\xe9`) and the new code writes UTF-8.

     Criterion 13 requires these differences ("writes UTF-8 regardless of the console code page").

   There are 0 blocks where HEAD succeeded and the new code fails.
2. **Stored data.** All 52 checkpoint files written by the CLI matrix are byte-identical between the two versions once `created_at` is ignored. The git commit subjects are identical too. The one intended difference is that new repos get local `core.autocrlf=false`.
3. **API + MCP with a fixed clock.** The script ran five saves:
   - the Unicode/CRLF checkpoint
   - one with `resumed_from`
   - a non-ASCII chat name with an API key, to exercise redaction
   - an empty checkpoint_name, which gives a ValidationError
   - a chat_name containing `/`, which gives a ValidationError

   It recorded the sha256 of every file, `git log` subjects with tree hashes, `git status`, and `list()`. It also rendered briefs and errors for 10 refs (`cp-001`, `trial/uni`, `uni`, `naïve/k`, `TRIAL/UNI`, `''`, `chat\name`, `cp-999`, `../x`, `a/b/c`). On the MCP side it recorded `list_tools()` (names, descriptions, input schemas) plus the list/get/resume/not-found tool calls. `diff api_old.json api_new.json` is empty: IDENTICAL, 21827 bytes each.
