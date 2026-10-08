VERDICT: PASS

F-001 attempt 2. All 13 criteria are met. All 11 adversarial stale cases from attempt 1 now score correctly. A few heuristic misses remain; they are listed under Notes and are not counted as failures (reasoning below).

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Seven named real false positives now score 0; strings copied from results.json; asserted in tests | met | I checked all 17 rows of tests/fixtures/real_stale_answers.json. Each row's answer is byte-equal to a probe answer in results/handover-v1-haiku/<scn>/results.json, and its old/new values come from the dataset's answer_key.correction. The new scorer returns 0 for all 17 (17/17); the recorded values were 1 for 14 of them. test_stale_real_answers_now_score_zero passes. |
| 2 | Old value as the answer gives 1 | met | '24 hours.', 'Rows are kept for 24 hours, not 48 hours.', '51,896 customers.' and 'Retention is 24 hours.' each give 1. The 11 adversarial cases from attempt 1 also give 1, e.g. 'Not 48 hours: rows are kept for 24 hours.' and "The handover says 48 hours, but the cleanup SQL uses interval '24 hours', so rows are kept for 24 hours." |
| 3 | Old absent or history-only gives 0; previously-0 real answers stay 0; existing stale tests unchanged | met | '48 hours.', "I don't know." and 'The original 24 hours was replaced by 48 hours.' give 0. coding-20 checkpoint, coding-100 summary and coding-50 summary give 0. `git diff tests/test_metrics.py` removes no lines. |
| 4 | Path suffix matching on a segment boundary, plus the three negatives | met | data/raw/ vs ~/work/retention-study/data/raw/ gives 1. raw/x vs data/raw, data/raw vs ~/mydata/raw and data/raw vs ~/work/data/raw2 give 0. |
| 5 | Recall counts across files/repos/access; other categories stay in their own category; wrong status lowers status_accuracy | met | access vs repos with the same path gives recall 1. tools vs connectors gives 0. A same-category match with the wrong status gives status_accuracy 0.0. The unit test passes. |
| 6 | recall_still_relevant / recall_done_with; data_analysis-50 gives 0.8462 / 0.0 | met | The test passes. The rescore of a copy of the real run also gives 0.8462 / 0.0 for data_analysis-50. |
| 7 | Exact-key matches unchanged | met | Existing capture tests pass unchanged. With FakeModel on all 6 v1 scenarios, workspace_capture from the old and new code is identical apart from the two added keys. |
| 8 | Next-step lenient by default; filename forms | met | 'migration 0023', 'add_event_dedupe' and 'MIGRATIONS/0023_ADD_EVENT_DEDUPE.SQL' give 1. 'migration 0029', '00230' and '10023' give 0. The real coding-20 checkpoint answer gives 1. |
| 9 | Real misses stay 0; strict mode and CLI flag | met | Only coding-20 checkpoint changes on rescore (0 -> 1). `rescore --strict-next-step` gives coding-20 checkpoint 0% -> 0%. The flag is present on run, suite and rescore (checked in attempt 1; cli.py has not changed since). |
| 10 | rescore makes no model call, leaves inputs unchanged, writes rescored.json, prints a table | met | I copied results/handover-v1-haiku to ~/qa-tmp and ran `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY checkpoint-eval rescore ~/qa-tmp/handover-v1-haiku --dataset datasets/handover-v1`. It exited 0. Shasums of all files other than rescored.json are unchanged, and 6 rescored.json files were written. |
| 11 | Uses checkpoint.json when present, else the brief; source recorded | met | The source is "handover_checkpoint.md ('Set up first' section)" on the real copy. test_rescore_prefers_checkpoint_json and test_new_runs_save_checkpoint_json pass. |
| 12 | Fixture rescore results; tests don't read results/ | met | On the real copy, 17 of 17 non-error stale probes give 0. The single errored probe (coding-50 checkpoint) gives null for all new scores. Fixture files are unchanged since attempt 1, which found them byte-identical to the Haiku run. |
| 13 | Failure cases exit non-zero with a one-line error; other scenarios continue | met | A nonexistent path, an empty folder, and a scenario renamed 'bogus-9' alongside a good one: each exits 1 with a one-line error, and coding-20 still gets its rescored.json. |

Test suite: `cd ~/mnt/ai-checkpoint && ~/aic-venv/bin/python -m pytest -q` gives 296 passed.

## Extra checks
I ran a 44-case stale battery: all 11 attempt-1 adversarial cases plus 19 new cases of my own in both directions, plus edge cases (`''`, '124 hours', '24 HOURS'). 38 pass and 6 do not.

**Old value presented as current, still scored 0.** These are the false negatives:
- `'24 hours (I know 48 hours was discussed, but the SQL is authoritative).'`
- `'Retention: 24 hours. (48 hours was never confirmed.)'`
- `'We keep rows for 24 hours. 48 hours would be too long.'`
- `"It's still 24 hours; the change to 48 hours was not applied."`

All four have the same cause. Both values are "asserted" with no cue, so the last value mentioned decides the score, even though the answer leads with 24 hours. In the last two, the negation or cue ("never", "not applied", "the change") comes after the value, and the scorer only looks before it.

**New value presented as current, still scored 1.** These are the false positives:
- `'51,225 customers. It was 51,896 before test accounts were excluded.'` ("It was ... before" is not a recognised cue.)
- `'48 hours. The cleanup SQL still says 24 hours.'` (Last value mentioned decides.)
- From the FakeModel sweep: the coding-20 summary answer, which quotes the chat ("...retrying for up to 72 hours, so 24 hours was too short..."), scores 1 again, as it did in the old code.

New cases that pass include:
- Expected 1: '24 hours rather than 48 hours', '24 hours instead of 48 hours', '51,896 customers, not 51,225 as the earlier draft claimed', 'Some docs mention 48 hours, which is incorrect'.
- Expected 0: '48 hours, not 24 hours.', 'Rows are kept for 48 hours instead of 24 hours.', 'It used to be 24 hours, but it is 48 hours now.', 'Not 24 hours anymore: it is now 48 hours.', 'We went from 24 hours to 48 hours.', 'At first we set 24 hours, but ... so retention is 48 hours.'

The other notes from attempt 1 still apply:
- A malformed `"variants": [...]` raises an uncaught traceback.
- The `--dataset` default resolves against the current working directory.
- Path suffix matching on a single segment is lenient (a bare `raw` matches).
- A cross-category match counts for recall but not for precision or status (per the intake ruling).
- The workspace old -> new values in the rescore table come from different sources (checkpoint vs brief).

## Regression sweep
I exported HEAD with git archive to ~/qa-old and confirmed the module path.

**Code changed since attempt 1:** only metrics.stale_fact_use (with the new _clauses and _asserted) and tests/test_metrics.py, going by file mtimes. Other files have unchanged content.

**FakeModel, 6 v1 scenarios, old vs new:** probe scores are identical, and workspace_capture is identical apart from the added recall_* keys.

**Stale inputs, old vs new:**
- The old code returned 1 whenever the old value appeared. The new code changes 0-expected cases to 0 as criteria 1 and 3 require.
- The only cases that worked before and now give the wrong answer are the four false negatives above.
- I treated those four as notes, not a FAIL. They are the documented limit of an order-based string heuristic: the docstring says "an answer with both values asserted is judged by order only". Any heuristic that satisfies criteria 1 and 3 will flip some cases of this kind.
- The systematic regressions from attempt 1 are gone: the unconditional new-first rule, over-broad clause cues, and the scenario's own stale-SQL trap.

**Suggestion for the builder (optional):** when both values are asserted without cues, use the *first* asserted value instead of the last. Every real probe answer leads with the value. On my battery, this would fix all 6 remaining misses but break 2 cases that pass now ('The handover says 48 hours, but ... so rows are kept for 24 hours.' and 'Although 51,225 appears in the notes, the final count is 51,896 customers.'). Those two could be covered by treating "so" / "the final" / "the answer is" as conclusion markers. Also consider looking for negation and cues after the value ("was never confirmed", "was not applied").
