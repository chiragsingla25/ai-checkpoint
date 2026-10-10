VERDICT: FAIL

## Verdicts
F-006: FAIL

## Test suite
`.venv/bin/python -m pytest -q` at HEAD 31c7ac4: **403 passed**, 0 failed (108 s; a second run gave 403 passed in 118 s). That is 402 plus the new `test_secret_leakage_same_in_bundle_and_old_modes`.

This is a re-check of F-006 only. The fix diff is BASE 4697925..HEAD 31c7ac4. Code touched: `src/ai_checkpoint/eval/pipeline.py`, where `_bundle_handover` now returns the parsed dict, `_checkpoint_handover` passes it on as `presave`, and `_workspace_capture` measures secret_leakage on it. One test was added to `tests/test_eval_bundle.py`. Nothing else in src/ changed.

## F-006 Eval support for the bundle path (offline)
| Criterion | Result | Evidence |
|---|---|---|
| 1. compaction_system_prompt() describes the new fields from the same schema source as the MCP tool (a test asserts this) | met | `test_prompt_contains_new_tool_field_descriptions` passed. schema.py and server.py are not touched by the fix, so the attempt-1 direct check still holds. |
| 2. Bundle path (temp store save, then resume); save-check errors recorded, not aborting | met | `test_handover_goes_through_a_bundle_store` and `test_still_rejected_after_retry_is_recorded_not_raised` passed. Direct check at HEAD: garbage then valid, invalid (`chat_name: "a/b"`) then valid, and invalid twice were all recorded in save_checks (rejected_first/retry_needed true, retry errors listed), and none raised. |
| Ruling 1: one retry with the errors, recorded in results.json | met | `test_rejected_save_gets_one_retry_with_errors_and_is_recorded` and `test_results_json_records_whether_retry_was_needed` passed. In the offline run, all 6 bundle results.json have `save_checks = {mode: bundle, rejected_first: false, retry_needed: false, first_errors: [], retry_errors: []}`. After a retry, leakage is measured on the attempt that was saved. Rejected leaky first attempt, then clean retry: leak 0. Rejected first attempt, then leaky retry: leak 1. |
| 3. FakeModel uses the new fields and passes the save checks | met | `test_fake_output_uses_new_fields_and_passes_save_checks` and `test_fake_passes_checks_on_every_v2_scenario` (6 cases) passed. models.py is unchanged. |
| 4. `checkpoint-eval suite datasets/handover-v2/*.json --model fake --out <tmp>` works offline | met | I unset ANTHROPIC_API_KEY and OPENAI_API_KEY and ran under `sandbox-exec ... (deny network*)`, after confirming the sandbox blocks a socket connect (`PermissionError: [Errno 1] Operation not permitted`). rc=0, with 6 scenario folders, each holding results.json and results.md (12 files). The checkpoint status is ok in all 6. |
| 5. Old-format path available; existing eval tests pass | met | Same sandboxed run with `--handover-format old`: rc=0, 6 folders, 12 files, all checkpoints ok, `save_checks == {mode: old}`. `test_old_format_flag_keeps_flat_path` passed, and the existing eval tests are among the 403. |
| 6. eval-runs/README.md documents a real v2 run; the real target is a separate manual run | met | `test_eval_runs_readme_documents_v2_run` passed. README is unchanged since attempt 1. |

Requested checks:
- **The attempt-1 reproduction now matches.** A leaking model appends the scenario secret to `context` on coding-20. secret_leakage is 1 on HEAD bundle, 1 on HEAD old, 1 on pre-F-006 (3a9e257) and 0 on BASE 4697925 bundle. The leak is also counted for a secret placed in `decisions` (1/1/1) and in `verbatim` (1/1/1).
- **The new test fails on e14e383.** I copied HEAD's `tests/test_eval_bundle.py` into an e14e383 worktree and ran `-k secret_leakage` with that worktree's src, confirming the module path. Result: `assert got["bundle"] == got["old"]` gave `E assert 0 == 1`, 1 failed. The test does catch the attempt-1 bug.
- **The results.md label is true only for the fields that both paths keep.** The coding-20 results.md still says "secret leakage is measured on the model's checkpoint before the product's save-time redaction". For secrets in fields the checkpoint keeps (context, decisions, verbatim), that is now true. For the inputs below it is not: the bundle path now measures the model's raw JSON before validation. That includes parts the product throws away or strips during validation, before any redaction.

Extra checks (adversarial, leaking model on coding-20, HEAD bundle / HEAD old / pre-F-006):
- `workspace.env_vars` item `{"name": "API_KEY=<secret>", "status": "still_relevant"}`: **1 / 0 / 0**. The product keeps names only, so it reduces this to `API_KEY`. I switched off `redact_obj` in store.py and ran the bundle save. The stored checkpoint has `{'name': 'API_KEY', ...}` and the secret is nowhere in the checkpoint or the brief. The secret never reaches the checkpoint, even before redaction, but bundle mode still reports a leak. This is the likeliest real way a model would write a secret in these scenarios.
- Unknown top-level key `"notes_extra": "<secret>"`: **1 / 0 / 0**. store.save drops the key, but bundle mode counts the leak.
- `user_turns: ["my key is <secret>"]`: 1 / 0 / 0. This is a note only. The bundle checkpoint does keep user_turns (it redacts them at save), so counting this is consistent with the label. The flat model has no user_turns field, so the difference is built into the two modes.

## Regression sweep
BASE 4697925 compared with HEAD 31c7ac4. I ran BASE from a `git worktree` with its src first on sys.path and confirmed the module path. Code paths touched: `_bundle_handover` (return value), `_checkpoint_handover` (bundle branch), `_workspace_capture` (secret_leakage source).

Inputs compared:
- Full offline suite with the fake model on all 6 handover-v2 scenarios, in both `--handover-format bundle` and `old`. `diff -rq` of the HEAD and BASE output folders found no differences in either mode. All other capture scores are unchanged.
- Leaking-model placements on coding-20, bundle mode, BASE then HEAD: context 0 → 1 and decisions 0 → 1. The fix exists to make these changes, and the label requires them. verbatim 0 → 1, same reason.
- **Differences not required:** env_vars `NAME=<secret>` went 0 → 1 and an unknown key holding the secret went 0 → 1. For both, old mode and pre-F-006 report 0, and the product never stores the secret. Before the fix, bundle under-counted leaks. It now over-counts against the same label and against old mode. This is the same problem as attempt 1 in the other direction: secret_leakage still means different things in the two modes. The comparison between v2 and old runs counts against v2 exactly in the case (env var values) the metric is meant to catch.

Worktrees for 4697925, 3a9e257 and e14e383 were removed and `git worktree prune` was run. Scratch output and scripts were deleted. `git status` is clean.

## For the builder (failing features only)
F-006:
1. **Bundle-mode secret_leakage counts secrets that never reach the checkpoint, so it still differs from old mode and pre-F-006.**
   - Reproduce: on coding-20, use a FakeModel subclass whose compaction JSON appends `{"name": "API_KEY=" + scenario.secret_values[0], "status": "still_relevant"}` to `workspace.env_vars`. Run `run_scenario(sc, model)["workspace_capture"]["secret_leakage"]`: you get 1 in bundle mode and 0 with `handover_format="old"` (pre-F-006 also gives 0). A top-level unknown key holding the secret does the same (1 vs 0).
   - Cause: `_workspace_capture` scores `json.dumps(presave)` and `presave["workspace"]`, which are the raw model output before validation. The old path scores `Checkpoint.from_dict(parsed).to_dict()`, which is validated and normalised (env var values stripped, unknown keys dropped) but not redacted.
   - Correct: in bundle mode, measure the checkpoint as the product would store it, after validation and normalisation but before `redact_obj`. That way the number matches old mode on every field both modes keep, and the "before save-time redaction" label holds. For example, run the same validation store.save uses on the unredacted dict, or capture the validated checkpoint before redaction. Extend `test_secret_leakage_same_in_bundle_and_old_modes` to cover the env_vars `NAME=<secret>` case and an unknown key. For both, assert bundle == old == 0, while the context case stays bundle == old >= 1. The user_turns case is a real difference between the modes (only bundle keeps user_turns). If you keep it, say so in the build log.
