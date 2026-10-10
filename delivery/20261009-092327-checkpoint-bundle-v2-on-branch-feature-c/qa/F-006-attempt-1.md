VERDICT: FAIL

## Verdicts
F-006: FAIL

## Test suite
`.venv/bin/python -m pytest -q` at HEAD 4697925: **402 passed** in 101s, 0 failed. This includes tests/test_eval_bundle.py (new) and all the existing eval tests. tests/test_runner.py was changed only to allow the new `save_checks` key on the checkpoint variant.

## F-006 Eval support for the bundle path (offline)
| Criterion | Result | Evidence |
|---|---|---|
| 1. compaction_system_prompt() describes the new structured fields from the same schema source as the MCP tool (a test asserts this) | met | `test_prompt_contains_new_tool_field_descriptions` checks that the FIELD_DESCRIPTIONS entries for tasks, tasks.quote, tasks.from, user_turns, facts, open_questions.waiting_on_user, decisions.supersedes and workspace appear in the prompt. server.py builds its tool fields from the same `FIELD_DESCRIPTIONS` (`FD = FIELD_DESCRIPTIONS`). Direct check: I walked the live `save_checkpoint` inputSchema from `create_server()`. 53 of its 59 description strings appear verbatim in the prompt. The 6 that don't are resume-only (`resumed_from`, `plan_updates` and its id/text/depends_on), which is consistent because the prompt tells the model to set resumed_from to null. The sixth is WsEnvVar.name, a hard-coded string in server.py (note below). |
| 2. Handover built via the bundle path (temp store save, then resume); save-check errors recorded, not aborting | met | `test_handover_goes_through_a_bundle_store` uses a spy on GitStore.save and checks that a `chats/*/checkpoints/cp-*` bundle is written. `test_still_rejected_after_retry_is_recorded_not_raised` shows status=failed with an error, while summary still runs. Code: `store.save()` then `store.get()` inside a TemporaryDirectory. Adversarial inputs below are all recorded, none abort. |
| Ruling 1: one retry with the error messages, recorded in results.json | met | `test_rejected_save_gets_one_retry_with_errors_and_is_recorded` checks exactly 2 compaction calls, that the retry prompt contains "Save rejected" plus the offending quote, and rejected_first/retry_needed/first_errors. `test_results_json_records_whether_retry_was_needed` covers results.json. Direct run: all 6 results.json have `variants.checkpoint.save_checks = {mode: bundle, rejected_first: false, retry_needed: false, first_errors: [], retry_errors: []}`. |
| 3. FakeModel uses new fields (from=user quotes verbatim, user_turns, workspace with done_with) and passes save checks | met | `test_fake_output_uses_new_fields_and_passes_save_checks` checks that the quote is a substring of a user turn, user_turns is present and next_steps absent. `test_fake_passes_checks_on_every_v2_scenario` (6 cases) checks for a done_with workspace item, no rejection, and "Next action" in the brief. The direct run's coding-20 brief shows `[t-1] ... The user said: "I have to stop for today."` |
| 4. `checkpoint-eval suite datasets/handover-v2/*.json --model fake --out <tmp>` completes offline, no key, no network, results.json + results.md for all 6 with a checkpoint handover | met | Ran `env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY sandbox-exec -p '(version 1)(allow default)(deny network*)' .venv/bin/checkpoint-eval suite datasets/handover-v2/*.json --model fake --out <scratch>/new`. I confirmed beforehand that the sandbox blocks sockets (`PermissionError: Operation not permitted`). rc=0. All 6 folders contain results.json, results.md, handover_checkpoint.md and checkpoint.json, and the checkpoint status is ok in all 6. results.md has the line "Save checks (checkpoint variant): passed on the first try". `rescore` on the output also works (rc=0) and keeps save_checks. |
| 5. Old-format path available; existing eval tests pass | met | Ran `--handover-format old` on the same 6 scenarios under the same no-network sandbox: rc=0, all checkpoint variants ok, `save_checks == {"mode": "old"}`. `test_old_format_flag_keeps_flat_path` passes. The existing eval tests are part of the 402 that passed. |
| 6. eval-runs/README.md documents a real v2 run; the real target (>=90% next step, >=88% recall) is a separate manual run | met | The README section "Running the bundle (v2) checkpoint for real" gives the offline smoke command, the real `--model anthropic` command, the `--handover-format old` option and the "Release target (a separate MANUAL run, not an offline test)" line. `test_eval_runs_readme_documents_v2_run` passes. |

Extra checks (adversarial compaction outputs through `build_handovers`, bundle path):
- Garbage twice, empty string, JSON list, `chat_name: "a/b"`, missing objective, `resumed_from: "cp-999"`: each got exactly one retry (2 calls). Each was recorded with rejected_first/retry_needed=true and 1 retry error, and none raised.
- Garbage, then valid: recovers, error=None, retry_errors=[].
- `run_scenario(..., workers=4)` with garbage twice: checkpoint status=failed, retry recorded, no abort.
- A secret in the context: save passes and is redacted. This is the source of the regression below.

Notes (not failures):
- In bundle mode, checkpoint.json is `cp.to_dict()` of the flat checkpoint that `store.get` returns. It has `tasks: null` and no `user_turns`, so the structured fields the model produced are not in the eval artefact. No criterion requires this.
- With the fake model, checkpoint next-step accuracy on coding-100 and data_analysis-100 drops from 100% (BASE) to 0% (bundle). The cause is that FakeModel's heuristic answerer now picks up the brief's "Start by telling the user..." boilerplate. This is a fake-model artefact, not a criterion. It is a reminder that offline fake numbers say nothing about the real target.
- The tool's `WsEnvVar.name` description ("The variable NAME only, never its value.") is hard-coded in server.py, not taken from FIELD_DESCRIPTIONS, and does not appear in the prompt.

## Regression sweep
BASE 3a9e257 vs HEAD (F-006 = e14e383). I ran BASE from a `git worktree` with `PYTHONPATH=<worktree>/src` and confirmed the module path. Touched code paths: eval/cli.py (new flag, plumbing), eval/models.py FakeModel compaction output, eval/pipeline.py (`_compaction_handover` refactor, new `_bundle_handover`, `_checkpoint_handover`, `build_handovers`, `run_scenario`, `save_checks` in results), eval/report.py (`markdown_table` note).

Inputs compared: the 6 handover-v2 scenarios with the fake model. Runs were BASE default, HEAD `--handover-format old` and HEAD default (bundle).
- Top-level results.json keys are identical. Only the checkpoint variant differs, and the summary and full_history variants are byte-identical.
- HEAD old vs BASE: the checkpoint briefs differ only where FakeModel now emits `tasks` (for example "1. User's plan: Continue with: ..." instead of "1. Continue with: ..."). Criterion 3 requires that change. The old-path code itself is an unchanged refactor.
- **Difference found, not required by any criterion.** The secret_leakage metric changed meaning on the default path. I used a FakeModel subclass that appends the scenario's secret (`sk-fake-290d...`) to `context` on coding-20:
  - BASE default: `secret_leakage = 1`
  - HEAD `--handover-format old`: `secret_leakage = 1`
  - HEAD default (bundle): `secret_leakage = 0`

  The bundle path measures leakage on `store.get()` output, which store.save has already redacted. results.md still prints "secret leakage is measured on the model's checkpoint before the product's save-time redaction" and "secret leakage (distinct secrets, before save-time redaction)". On the default path that label is now false, and a model that leaks secrets will always score 0.

Worktree removed and scratch output deleted. No files outside RUN were left behind.

## For the builder (failing features only)
F-006:
1. **The secret-leakage metric is silently measured after redaction on the bundle path.**
   - Reproduce: take a FakeModel subclass whose compaction JSON gets `context += " The API key is " + scenario.secret_values[0]`. Call `run_scenario(load_scenario("datasets/handover-v2/coding-20.json"), model)`. `workspace_capture.secret_leakage` is 0, but 1 with `handover_format="old"` and 1 at BASE. results.md still says the number is "before save-time redaction".
   - Correct: in bundle mode, measure leakage on the model's parsed compaction output before `store.save()` (for example the parsed dict of the accepted attempt), as the label says and as BASE did. If the post-redaction number is also wanted, report it separately with its own label. Add a test with a leaking model that asserts secret_leakage >= 1 on the bundle path.
