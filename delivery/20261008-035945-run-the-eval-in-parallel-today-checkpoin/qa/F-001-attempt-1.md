VERDICT: PASS

Scratch: outputs under $HOME/qa-tmp, HEAD exported to $HOME/qa-old via `git archive HEAD | tar -x` (old module confirmed at $HOME/qa-old/src/ai_checkpoint/eval/cli.py). C = $HOME/aic-venv/bin/checkpoint-eval, D = datasets/handover-v1.

| Criterion | Result | Evidence |
|---|---|---|
| 1. --help lists --workers N, default 8; omitted = 8 | met | `C run --help` and `C suite --help` both show `--workers N  maximum model calls in flight at once, across all scenarios (default 8; 1 = fully sequential)`. Suite with no --workers (`--out Sdef`): `diff -r S1 Sdef` empty, stdout identical, stderr interleaved like w8; in-flight peak with default matches 8 (see 6). |
| 2. --workers 0 / -1 / abc exit 2, argparse error, no output | met | run and suite x {0,-1,abc}: rc=2, stderr `checkpoint-eval run: error: argument --workers: must be at least 1` / `'abc' is not a whole number`; `ls -d bad_*` -> none. Extra inputs `1.5` and `''` also rc=2, no dir. |
| 3. Byte-identical outputs across workers 1/2/3/8 (suite and run) | met | `C suite D/*.json --workers N --out SN` for N=1,2,3,8,default: `diff -r S1 SN` empty for all; same for `run coding-50.json` R1 vs R2/R3/R8. With FAKE_DELAY=0.5 (real overlap) T-1 vs T-8 also identical and equal to no-delay output. |
| 4. --workers 1 identical to pre-change code | met | Old code (PYTHONPATH=qa-old/src) `suite D/*.json --out Sold`: `diff -r Sold S1` empty, `cmp soold so1` equal, stderr identical after stripping the elapsed-time field. Old `run coding-50` == new run w1 == new run default (files and stdout). |
| 5. suite stdout w8 == w1, command-line order, one blank line between tables | met | `cmp so1 so8` equal (and equal to old code's stdout, which already defines the separator); also equal for w2/w3/default and under FAKE_DELAY where completion order differs. |
| 6. In-flight cap <= N and reaches N | met | Own wrapper model counting concurrent complete() (FAKE_DELAY=0.05, 6-scenario suite): peak 1/2/3/5/8 for N=1/2/3/5/8. N=20 -> peak 18 (=6 scenarios x 3 concurrent chains, the structural max). Builder test test_in_flight_cap also passes. |
| 7. Within-scenario overlap/ordering | met | Own timing script (patched Caller.call, FAKE_DELAY=0.3, run --workers 8): summarize (0.01-0.31), compact (0.01-0.34), answer full_history (0.01-0.35) all start together; judge full_history starts 0.35 (before answer checkpoint ends 0.65); each judge starts after its own answer ends. Also checked --workers 2: still correct ordering, full_history waits on the cap as expected. |
| 8. Progress lines whole, k = 1..total once each, same line count | met | Regex checker over stderr of w1, w8, default, FAKE_DELAY w1/w8 (two runs), FAIL_FIRST w8: 48 lines each, 0 non-matching lines, 6 scenarios, k per scenario exactly 1..8. |
| 9. Timing (FAKE_DELAY=0.5, 48 calls): ~24s w1, <5s w8 | met | Two runs: w1 24.76s / 24.81s; w8 3.29s / 3.26s. Not flaky. |
| 10. Timeout and retry per call under w8 | met | FAIL_FIRST=1: w1 and w8 rc=0, 48 `(after retry)` lines each, outputs/stdout identical to each other and to the clean run. FAKE_DELAY=0.4 --timeout 0.1: rc=1, empty stdout, `FAILED after 2 attempts (timeout)` present, and the 6 `error: scenario X: compact call failed after 2 attempts: timeout: ...` lines are identical to old code's. |
| 11. Failure isolation | met | (a) OUT/coding-50 pre-created as a file, default workers: rc=1, `error: scenario coding-50: [Errno 17] File exists: 'I8/coding-50'`, other 5 scenario folders `diff -r` equal to clean run, stdout equals clean stdout minus the coding-50 table, order kept. (b) Own model injecting a compaction failure for coding-20 only, --workers 8: rc=1, `error: scenario coding-20: compact call failed after 2 attempts: qa injected compaction failure`, 5 tables, other 5 folders identical to clean. |
| 12. Only eval/, tests/ (docs) touched | met | `git status`: M src/ai_checkpoint/eval/{cli,models,pipeline}.py, M tests/test_runner.py, ?? tests/test_eval_parallel.py (plus the delivery run folder). Nothing in save/resume/MCP modules. |
| 13. Full test suite passes plus new tests | met | `python -m pytest -q` -> 282 passed in 46.5s (259 + 23 new in tests/test_eval_parallel.py covering criteria 1-11). |

## Extra checks
- Edited existing test (tests/test_runner.py::test_progress_lines_on_stderr_only now passes `--workers 1`): justified. The test asserts exact stage order `compact, summarize, answer, judge, ...` which is only defined for sequential runs; under the new default it is legitimately completion-ordered. The "progress on stderr only, not stdout, 8 lines, [1/8]..[8/8]" property for the parallel default is covered by test_progress_lines_whole_and_counted and my regex checks, so coverage is not weakened.
- Bad --workers values beyond the spec: `1.5`, empty string -> rc 2, no output.
- No docs mention eval CLI options (no `--timeout` in any README), so no doc update was needed.

## Regression sweep
Touched: cli._workers (new), cli._common (new option), cli._run_one / _run / _suite (thread pool + ordered reporting), pipeline.Caller (__init__, _say now increments count at completion under a global lock, new _attempt with limiter, call), build_handovers (split into _checkpoint_handover/_summary_handover/_full_handover), run_scenario (+_eval_variant, parallel branch), models.FakeModel FAIL_FIRST bookkeeping (lock).
Old vs new compared: full suite (clean), single run, FAIL_FIRST suite outputs, timeout suite error lines, stderr modulo timings — all identical for --workers 1; files/stdout identical for default/8. No differences that a criterion does not require.

Notes (not failures):
- Under --workers > 1, when compaction fails the scenario's summary and full_history chains still run (wasted calls) and extra progress lines appear: timeout suite printed 18 `FAILED ... (timeout)` lines with w8 vs 6 with w1. The per-scenario `error:` lines and exit code are unchanged. Builder documented this.
- Elapsed time in progress lines counts from scenario start including time waiting on the shared cap (e.g. a scenario's first line can read 1.0s with a 0.5s call). Cosmetic.
- Failed-scenario error lines print only after all earlier scenarios finish (ordered reporting); documented.
- Builder moved a stale .git/index.lock to .git/stale-index-lock-aic (empty file); harmless but should be removed once deletion is permitted.
