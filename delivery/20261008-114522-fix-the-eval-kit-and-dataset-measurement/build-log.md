
## F-001 attempt 1
- What changed:
  - src/ai_checkpoint/eval/metrics.py: stale_fact_use rewritten (old-first and not framed as history -> 1; new first / history cue / old absent -> 0; new absent -> 1); next_step_correct lenient by default with `strict=` (filename term also matches stem, descriptive part, leading number on digit boundaries); score_probe(strict_next_step=); capture_scores with path-segment suffix matching, files/repos/access cross-category recall, recall_still_relevant / recall_done_with; workspace_from_brief() parses the brief's "Set up first" section.
  - src/ai_checkpoint/eval/rescore.py (new): `rescore` command logic, writes rescored.json, prints old -> new tables.
  - src/ai_checkpoint/eval/cli.py: `rescore` subcommand; `--strict-next-step` on run, suite, rescore.
  - src/ai_checkpoint/eval/pipeline.py: strict_next_step plumbed through run_scenario; result carries `_checkpoint`.
  - src/ai_checkpoint/eval/report.py: writes checkpoint.json; workspace table gains two recall columns.
  - tests: new tests in tests/test_metrics.py, new tests/test_rescore.py; fixtures tests/fixtures/real_stale_answers.json, real_next_step_answers.json, data_analysis-50.set_up_first_workspace.json, rescore/ (coding-20, coding-50, data_analysis-50 results + briefs + dataset files; copied from the Haiku run).
- How to run it: `checkpoint-eval rescore results/handover-v1-haiku [--dataset datasets/handover-v1] [--strict-next-step]`
- Tests: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q` -> 295 passed (282 original + 13 new). Ran rescore on a copy of the real Haiku run: all 17 non-error stale answers now 0, coding-20 checkpoint next-step 0 -> 1, data_analysis-50 recall_still_relevant 85% (11/13), recall_done_with 0%.
- User-visible changes: workspace-capture JSON and markdown table gain recall_still_relevant / recall_done_with columns; new runs also write checkpoint.json beside results.json; next-step scoring is lenient by default (use --strict-next-step for old behaviour); capture_recall/precision values can rise for the same checkpoint (suffix + cross-category matching).
- Notes: status_accuracy and precision compare within the manifest item's own category (cross-category counts for recall only, per intake). Stale history cues are a regex list in metrics.py (_HISTORY_CUE). Brief-based rescoring of workspace has no done_with items by construction, and its numbers are not comparable to the original checkpoint-based ones (source recorded in rescored.json). Rescore of a dir with a results.json lacking probes aligned to the scenario errors for that scenario only.

## F-001 attempt 2
- What changed: src/ai_checkpoint/eval/metrics.py only (stale scorer). stale_fact_use now cuts the answer into clauses and decides which value the answer ASSERTS: an occurrence counts unless its clause has a history cue or it is negated ("not 48 hours"; a following "but that is outdated" clause also marks the previous one as history). Old only asserted -> 1; both asserted -> the last asserted value (the conclusion) decides; old absent/history/negated -> 0; old present with no new -> 1 (unchanged). Heuristic and known limits are documented in the docstring. Removed bare "now"/"instead"/"rather than" as history cues; added considered/proposed/suggested/thought/assumed.
- How to run it: unchanged (`checkpoint-eval rescore ...`).
- Tests: `$HOME/aic-venv/bin/python -m pytest -q` -> 296 passed. New test_stale_old_value_asserted_as_current_despite_new_mentioned covers QA's cases plus negation/adversarial ones; all 17 real Haiku answers still 0.
- User-visible changes: none beyond attempt 1 (stale scoring is stricter about history vs assertion).
- Notes: known heuristic limits listed in the docstring (cue anywhere in a clause marks the whole clause as history; source-attributed values count as asserted; English cues only).

## F-002 attempt 1
- What changed: src/ai_checkpoint/eval/pipeline.py: new `_list_with_count_retry` used by answer_probes and judge_answers (wrong item count -> one retry whose messages are the original request, the first reply as assistant turn, and a short user instruction naming the expected count; still wrong -> the existing "expected N answers/verdicts, got M" errors with M from the retry); `Caller.expect_extra_call()` bumps the progress total so the retry shows as [k/total+1]. tests/test_retry.py (new).
- How to run it: automatic in `checkpoint-eval run/suite`.
- Tests: `$HOME/aic-venv/bin/python -m pytest -q` -> 302 passed (all offline).
- User-visible changes: a retried call prints an extra progress line "(<variant>, retry)" and the total grows from 8 to 9 from that point (the earlier lines already printed keep "/8"); a mismatch can now cost one extra model call.
- Notes: unparseable JSON is not retried. If the retry call itself fails (CallFailed after its own 2 attempts) the first reply's count error is recorded instead of failing the variant. A retry also counts toward --workers limits as a normal call.

## F-003 attempt 1
- What changed:
  - src/ai_checkpoint/eval/generate.py: `VERSIONS`, `check_scenario(scn)` (case-insensitive substring self-check of probe key_facts, decision/reason/rejected, verbatim, correction, next step and required terms, manifest keys and reference urls, env var names, secrets); `generate_scenario/generate_dataset(..., version)`; the two story builders take `v2` and, only for handover-v2, state the decision, its rejected option and its reason in the chat in the answer key's words, say "Carrier webhook docs" and mention `ANALYTICS_DB_PATH`. The random stream is shared by both versions, so v2 has the same projects, numbers and filler as v1; `meta.generator` is the version.
  - src/ai_checkpoint/eval/cli.py: `generate --version {handover-v1,handover-v2}`; a bogus value exits 2 listing the valid versions.
  - datasets/handover-v2/ (6 scenarios + README.md with seed 7 and the regenerate command).
  - tests/test_dataset.py: new tests (self-check on v1 finds ANALYTICS_DB_PATH / Carrier webhook docs; v2 self-check is []; key phrases; v2 byte-identical regeneration; v1 reproducible with the flag; bogus version).
- How to run it: `checkpoint-eval generate --seed 7 --version handover-v2 --out datasets/handover-v2`
- Tests: `$HOME/aic-venv/bin/python -m pytest -q` -> 307 passed, offline. `git diff --stat` for datasets/handover-v1 and for src/ai_checkpoint outside eval/ is empty.
- User-visible changes: new `--version` option on `generate`.
- Notes: the CLI default stays handover-v1 (intake suggested v2) because the existing byte-identical test calls `generate` without --version and had to pass unchanged; flipping the default is a one-line change plus that test. v2 decision sentences are quoted verbatim in the chat (lower-cased first letter), which reads slightly formal but passes the literal self-check.
