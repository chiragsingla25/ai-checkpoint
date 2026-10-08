VERDICT: FAIL

F-001 attempt 1. 12 of 13 criteria are met. Criterion 2 is not met as written, and the change is a regression: the new stale scorer gives 0 to answers that present the old value as the current one. The orchestrator asked for this case to be checked specifically.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Seven named real false positives now score 0; fixture strings copied from results.json; asserted in tests/test_metrics.py | met | I checked all 17 rows of tests/fixtures/real_stale_answers.json. Each row's answer is byte-equal to a probe answer in results/handover-v1-haiku/<scn>/results.json, and its old/new values equal the dataset's answer_key.correction. New code scores 0 on all 17. Old code (HEAD export, PYTHONPATH=~/qa-old/src, module path confirmed) gives the recorded 1 on all 14 flagged rows. test_stale_real_answers_now_score_zero asserts this. |
| 2 | Stale scorer still returns 1 when the old value is the answer | **not met** | The four listed examples return 1. The general statement fails on answers outside that list (see "For the builder"). Example: `'Not 48 hours: rows are kept for 24 hours.'` gives 0 (the old code gave 1). This is the mirror of the listed `'24 hours, not 48 hours'` example. |
| 3 | Returns 0 when old is absent or is history before new; previously-0 real answers stay 0; existing stale tests unchanged | met | '48 hours.' gives 0, "I don't know." gives 0, 'The original 24 hours was replaced by 48 hours.' gives 0 (the old code gave 1). coding-20 checkpoint, coding-100 summary and coding-50 summary give 0. `git diff tests/test_metrics.py` has no removed lines. |
| 4 | Workspace path suffix matching on a segment boundary, with the three negative cases | met | data/raw/ matches ~/work/retention-study/data/raw/, and also matches the $HOME/... form (recall 1). raw/x vs data/raw, data/raw vs ~/mydata/raw and data/raw vs ~/work/data/raw2 all give recall 0. The old code gave 0 for the positive cases. |
| 5 | Recall counts across files/repos/access; other categories stay within their own category; a wrong status lowers status_accuracy | met | access ~/work/retention-study matched to repos gives recall 1, as do repos to files and files to access. tools to connectors, env_vars to tools, and files to tools give 0. A same-category match with the wrong status gives status_accuracy 0.0. Unit test test_workspace_cross_category_recall_and_status covers this. |
| 6 | recall_still_relevant / recall_done_with keys; real data_analysis-50 values are 0.8462 / 0.0 | met | test_recall_split_by_status_real_data_analysis_50 passes. The fixture workspace matches the 'Set up first' section of results/.../data_analysis-50/handover_checkpoint.md (I compared them by eye). The fixture dataset file is byte-identical to datasets/handover-v1/data_analysis-50.json. A manifest with no items of a status gives None. |
| 7 | Exact-key matches unchanged | met | All existing capture tests pass unchanged. With FakeModel on all 6 v1 scenarios, old and new workspace_capture are identical apart from the two added keys. |
| 8 | Next-step is lenient by default; filename variants | met | The real coding-20 checkpoint answer gives 1 lenient and 0 strict. 'migration 0023', 'add_event_dedupe' and 'MIGRATIONS/0023_ADD_EVENT_DEDUPE.SQL' give 1. 'migration 0029', '00230' and '10023' give 0. |
| 9 | Real misses still score 0; strict mode and `--strict-next-step` | met | coding-20 summary, coding-50 summary, data_analysis-100 checkpoint and summary, and data_analysis-20 summary all give 0. All other real answers keep their recorded score. `--strict-next-step` is present in `run`, `suite` and `rescore` --help. `rescore --strict-next-step` on coding-20 gives checkpoint next-step 0% -> 0%. |
| 10 | `rescore`: no model call; results.json and handover_*.md bytes unchanged; rescored.json per scenario; prints a table | met | I copied results/handover-v1-haiku to ~/qa-tmp and ran `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY checkpoint-eval rescore ~/qa-tmp/handover-v1-haiku --dataset datasets/handover-v1`. It exited 0, printed 6 old->new tables, and wrote 6 rescored.json files. The shasum of every other file was unchanged. The test also monkeypatches make_model to raise. |
| 11 | Uses checkpoint.json when present, otherwise the brief; source is recorded | met | On the real run (no checkpoint.json), the source is "handover_checkpoint.md ('Set up first' section)". test_rescore_prefers_checkpoint_json passes with source "checkpoint.json". test_new_runs_save_checkpoint_json confirms that new runs write checkpoint.json and that results.json does not contain _checkpoint. |
| 12 | Fixture rescore: stale 0, coding-20 checkpoint next-step 1, error probes null; tests don't read results/ | met | Fixture results.json and handover_checkpoint.md are byte-identical to the Haiku run. On the real copy, the coding-50 checkpoint ("expected 11 answers, got 12") has all-null new scores. No test file references results/handover. |
| 13 | Failure cases exit non-zero with a one-line error; one failing scenario doesn't stop the others | met | A nonexistent path, an empty folder, and a scenario renamed to 'bogus-9' in a mixed folder each exit 1 with a one-line error naming the path or scenario. The good coding-20 was still rescored. |

Test suite: `cd ~/mnt/ai-checkpoint && ~/aic-venv/bin/python -m pytest -q` gives 295 passed in 48.8s.

## Extra checks
- Leniency checks the orchestrator requested:
  - An unrelated path does not match (raw2, mydata/raw, raw/x).
  - A next-step answer missing the key action still scores 0 ('migration 0023 staging' gives 0, 'add staging replay' gives 0).
  - Old value presented as current: fails in several forms (below).
- The stale scorer handles '124 hours', '51,8960' and '' correctly (0), and '24 HOURS' gives 1.
- More rescore inputs:
  - A file given as the path: exit 1, "is not a folder".
  - Malformed JSON: exit 1, one line.
  - `[]`: exit 1, "no 'scenario' name".
  - Wrong probe count: exit 1, one line.
- Note: `"variants": [...]` (a list) raises an uncaught AttributeError traceback (rescore.py `results.get("variants").items()`), which would also stop the remaining scenarios. This is malformed input and not in the criteria.
- Note: the `--dataset` default `datasets/handover-v1` resolves against the working directory. Run from $HOME, it fails with "scenario coding-20 not found in datasets/handover-v1".
- Note: path suffix matching is symmetric. A checkpoint item that is a bare `raw` (or `src`) matches manifest `~/work/retention-study/data/raw`, which is quite lenient for single-segment paths.
- Note: a cross-category match counts for recall but not for precision or status. An access-vs-repos pair gives recall 1.0, precision 0.0 and status None, so a wrong status on such a pair is invisible. This matches the intake ruling (intake.md line 24), so it is not a FAIL.
- Note: rescore's workspace "old -> new" compares checkpoint-based old values with brief-based new values. On the real run, data_analysis-100 and -20 recall go 61% -> 56%. The source is recorded, but the table can read as a regression.

## Regression sweep
I compared HEAD exported to ~/qa-old (module path confirmed) with the working tree.
- Code paths touched:
  - metrics.stale_fact_use
  - next_step_correct
  - score_probe
  - capture_scores (and the new _paths_match, _keys_match, workspace_from_brief)
  - pipeline._eval_variant / run_scenario (strict flag, _checkpoint)
  - report.markdown_table / write_outputs (new columns, checkpoint.json)
  - cli (_common flag, rescore subcommand)
- run_scenario with FakeModel on the 6 v1 scenarios (old vs new results, _handovers removed):
  - Only differences: the added recall_* keys, and one stale probe (coding-20 summary) going 1 -> 0. That answer is "...retrying for up to 72 hours, so 24 hours was too short", which is history and correctly 0.
  - Verbatim scores, next-step scores, workspace capture recall/precision/status and secret leakage are unchanged.
- Next-step: of 17 real answers, only coding-20 checkpoint changed (required).
- Stale: **regression.** Inputs that the old code scored 1, where the answer clearly presents the old value as current, now score 0:
  - `'Not 48 hours: rows are kept for 24 hours.'` 1 -> 0
  - `'48 hours was considered, but the answer is 24 hours.'` 1 -> 0
  - `"The handover says 48 hours, but the cleanup SQL uses interval '24 hours', so rows are kept for 24 hours."` 1 -> 0. This is exactly the trap the coding scenarios set, since the stale SQL keeps 24 hours.
  - `'Although 51,225 appears in the notes, the final count is 51,896 customers.'` 1 -> 0
  - `'The current figure is 51,896 customers, updated from 51,225.'` 1 -> 0
  - `"24 hours. The handover's updated value of 48 hours is wrong."` 1 -> 0
  - `'Previously I thought 48 hours, but it is 24 hours.'` 1 -> 0
- Still correct (1): 'It is 24 hours; some notes say 48 hours but that is outdated.', 'Use 24 hours (the 48 hours figure was a draft).', 'The current retention is 24 hours. 48 hours was proposed earlier.'

## For the builder (FAIL only)
**Problem:** stale_fact_use (src/ai_checkpoint/eval/metrics.py) under-reports stale answers.

Reproduce with:
`~/aic-venv/bin/python -c "from ai_checkpoint.eval.metrics import stale_fact_use as s; print(s('Not 48 hours: rows are kept for 24 hours.','24 hours','48 hours'), s('48 hours was considered, but the answer is 24 hours.','24 hours','48 hours'), s(\"The handover says 48 hours, but the cleanup SQL uses interval '24 hours', so rows are kept for 24 hours.\",'24 hours','48 hours'), s('Previously I thought 48 hours, but it is 24 hours.','24 hours','48 hours'), s(\"24 hours. The handover's updated value of 48 hours is wrong.\",'24 hours','48 hours'))"`
It prints `0 0 0 0 0`. The expected output is `1 1 1 1 1`.

There are three causes:
1. **New-first is unconditional.** When `new` appears before `old`, the function returns 0 without looking at how `old` is framed. "new first" is not the same as "old is history". The answer's leading value, or the value asserted as the answer, matters more. The real answers that should be 0 all *lead* with the new value ("72 hours. ...", "51,225 customers ..."), while these failures lead with or conclude on the old one.
2. **The cue check for old's own clause is too broad.** The clause boundary ignores commas and "but", so "Previously I thought 48 hours, but it is 24 hours" sees "Previously" and returns 0. Restrict the cue to text that directly modifies `old` (for example, a small window just before it), or treat a cue that applies to `new` as evidence *for* staleness.
3. **Old-first with any cue between old and new returns 0.** This happens even when the cue condemns `new` ("updated value of 48 hours is wrong").

Correct behaviour: these cases return 1, while all 17 real answers in tests/fixtures/real_stale_answers.json and the criterion 2/3 examples keep their current results. Please add these strings as tests. One option is to score from the answer's leading value (the first value stated, usually before the first period) and fall back to the current rules only when neither value leads.
