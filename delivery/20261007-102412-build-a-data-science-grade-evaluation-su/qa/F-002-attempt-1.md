VERDICT: PASS

QA for F-002 (runner fixes and batched probes), attempt 1. I checked the uncommitted working tree against HEAD 7c02e5b. `ai_checkpoint.eval.pipeline.__file__` resolves to the working tree under mnt/ai-checkpoint/src. All 11 criteria are met.

| Criterion | Result | Evidence |
|---|---|---|
| 1. `run --help` lists `--timeout` (default 120) and `--force`; `--model`, `--model-name`, `--out` unchanged | met | `checkpoint-eval run --help` shows `--timeout TIMEOUT ... (default 120)`, `--force`, and `--model {fake,anthropic,openai}`, `--model-name`, `--out` as before. `--timeout=0`, `-1` and `abc` are argparse errors. |
| 2. Timeout bounded and retried once; DELAY=3 with timeout 1 returns within 10 s and names `timeout` and 2 attempts | met | `CHECKPOINT_EVAL_FAKE_DELAY=3 checkpoint-eval run invoice-sync.json --timeout 1` gave rc=1 in 2.09 s. stderr: `compact [1/8] 2.0s FAILED after 2 attempts (timeout)` and `error: compact call failed after 2 attempts: timeout: no reply within 1s`. No output folder was written. A timeout in the answer stage (only the summary variant sleeps 3 s, timeout 0.5) took 2 attempts in 1.0 s, recorded `summary: failed, 'answer call failed after 2 attempts: timeout ...'`, and the other variants finished. |
| 3. FAIL_FIRST=1 gives exit 0 and results.json identical to a normal run; a call that fails twice is not retried again (test) | met | With FAIL_FIRST: rc=0 and `cmp` reports results.json identical; results.md and all handover_*.md are also identical. stderr shows `(after retry)` on all 8 calls. `tests/test_runner.py::test_call_failing_twice_is_not_retried_a_third_time` asserts exactly 6 answer calls (3 variants x 2 attempts), and it passes. |
| 4. No overwrite without `--force`; `--force` replaces; new or empty folder behaves as before | met | Re-running into the same folder gave rc=1 with `error: .../base/results.json already exists; use --force to replace it`, and the md5 was unchanged. After I corrupted the file, `--force` gave rc=0 and the result was byte-equal to a fresh run. An empty folder gave rc=0. A folder holding only results.md gave rc=0. |
| 5. `suite` writes one folder per scenario with results.json, results.md and handover_*.md, prints one table per scenario, applies the overwrite rule per folder, and exits 1 on duplicate names before any call | met | `suite datasets/handover-v1/*.json --model fake --out S` gave rc=0, 6 folders each with the 5 files, and 6 tables on stdout. A re-run gave rc=1 (`... coding-100/results.json already exists ... (and 5 more)`). A pre-existing `coding-20/results.json` alone also blocks the whole suite before any run. Duplicate names: coding-20 twice and invoice-sync plus a copy both gave rc=1 `duplicate scenario name(s)`. With FAKE_DELAY=5 that exit came instantly and no out folder was created, so no model call was made. |
| 6. Batched: one answer call per variant with only the handover plus the questions; one judge call; exactly 8 calls whatever the probe count | met | A counting FakeModel subclass recorded 8 calls for invoice-sync (7 probes), delivery-restructure (7), coding-100 (11) and data_analysis-100 (11). It also recorded 8 calls for a 1-probe variant and for a 70-probe variant (probes x10). Every answer call's only message is `{"questions": [all probe questions]}`. The checkpoint and summary answer system prompts do not contain the transcript; only full_history does, because that transcript is its handover. |
| 7. One progress line per call on stderr with name, stage, `[n/8]` and elapsed time; stdout carries only tables | met | Example line: `[coding-100] answer (checkpoint) [3/8] 0.0s`. The suite run wrote 48 stderr lines (6 x 8) and 0 progress lines on stdout. |
| 8. results.json keeps the same keys and per-probe structure; the existing results/results.json still loads | met | The top-level, per-variant (`aggregate`, `error`, `handover_chars`, `probes`, `status`) and per-probe keys are identical between the old and new code (see the regression sweep). `markdown_table(json.load(open('results/results.json')))` renders the stored gemini run. |
| 9. Bad batched replies do not crash | met | I injected 11 reply faults: answer garbage, empty, too short, too long, an object instead of a list, non-string entries, a single null entry, judge too short, judge garbage, judge truncated mid-JSON, and judge entries that are not dicts. None crashed and every run wrote results.json and its table. The affected probes have `error` and null scores; the single null entry marks only that one probe. |
| 10. Existing behaviour: invoice-sync exits 0, prints the table and writes the files; two runs are byte-identical; the test suite passes; the test edits keep the handover-and-questions check | met | rc=0. `diff -r` of two output folders and `cmp` of the two stdouts are both identical. `pytest -q` gives 239 passed in 31.9 s. The test edits are reviewed under Extra checks. |
| 11. `--model openai` honours `OPENAI_BASE_URL` and the timeout (stub SDK, no network) | met | A stub `openai` module on PYTHONPATH logged `init {"timeout": 7.0, "base_url": "https://openrouter.ai/api/v1"}` and the model was `qwen/qwen3` (2 attempts, then a clean rc=1 error). Without the env var there is no base_url. A stub that sleeps 10 s with `--timeout 1` returned in 2 s with `FAILED after 2 attempts (timeout)`. |

## Extra checks
- **Changes to existing tests (tests/test_eval.py).** All four edits reflect the batched pattern:
  - `err == ""` became an assertion of exactly 8 progress lines on stderr. This is required by criterion 7.
  - The answer-isolation test now adds a second probe and asserts that each of the 3 answer calls' messages equal `{"questions": [both]}`. It keeps the three handover-prefix checks and adds `len(calls) == 8`. This is stronger than before.
  - Its recall assertion moved from `full_history aggregate == 1.0` to `probes[0] == 1.0`. With the added "Which host?" probe the aggregate is no longer guaranteed to be 1.0, so this is a narrowing that follows from the new probe, not an unrelated weakening.
  - Three SDK stubs now accept `**kw`, which they need for the new `timeout=` argument.
  - No other assertions were touched.
- New test file tests/test_runner.py has 23 tests covering the criteria. I re-checked every criterion independently rather than relying on these.

## Regression sweep
Code paths touched:
- models.py: `call_with_timeout`, FakeModel batched answer and judge, FakeModel fault injection, OpenAI/Anthropic constructors, `make_model`.
- pipeline.py: `Caller`, `extract_json_list`, `_compaction_handover`, `build_handovers`, `answer_probes` (which replaces `answer_probe`), `judge_answers`, `judge_answer` (now a batch of one), `run_scenario`.
- cli.py: shared options, `_run`, `_suite`, `main`.

I ran the HEAD code from worktree $HOME/qa-wt5 (confirmed `cli.__file__` in qa-wt5/src) and the working tree side by side:
- **Example and generated scenarios.** For invoice-sync, delivery-restructure, coding-20 and data_analysis-100 with `--model fake`, all handover_*.md, results.json and results.md files are byte-identical between old and new. So the batched FakeModel answers and verdicts reproduce the per-probe ones exactly.
- **Error paths: identical messages and exit codes.** I compared:
  - `--out` pointing to an existing regular file (rc 1, Errno 17)
  - a missing scenario file (rc 1)
  - invalid JSON (rc 1)
  - a scenario with no messages (rc 1)
  - `--model bogus` (rc 2)
  - `--model anthropic` with no key (rc 1)
  - bare `run` (rc 2)
  - `generate --seed 7` (rc 0)
- **No uncovered regressions.** The only behaviour changes found are ones the criteria require: refusing to overwrite, progress lines on stderr, and the new prompt format.
- `answer_probe` was removed and nothing else in the repo references it.

## Notes (not failures)
- The progress elapsed time is measured from the start of the scenario, not per call. The criterion says only "elapsed seconds", so this is acceptable, but a per-call duration would be more useful when diagnosing a slow call.
- When the answer reply is unusable, the judge call is skipped, so that scenario makes fewer than 8 calls. The counter total stays at `/8`.
- `extract_json_list` scans for the first array, so a truncated judge reply can yield an inner array (`expected 7 verdicts, got 3`). It is still marked as an error, which is the correct outcome.
- A timed-out call leaves a daemon thread running. That is harmless for a CLI process but could matter for long library use.
- `run_scenario` now guards with a 120 s timeout by default, even for callers that call the library directly.
- Scratch files ($HOME/qa-tmp) and the worktree were removed, and `git worktree prune` was run.
