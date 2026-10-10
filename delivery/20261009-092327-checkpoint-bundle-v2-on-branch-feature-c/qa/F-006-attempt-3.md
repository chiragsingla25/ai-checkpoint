VERDICT: PASS

## Verdicts
F-006: PASS

## Test suite
`.venv/bin/python -m pytest -q` at HEAD 3eed7aa: **409 passed**, 0 failed, in 121 s. That is 403 plus 6 new parametrised cases in `tests/test_eval_bundle.py`.

This is a re-check of F-006 only. The fix diff is BASE 31c7ac4..HEAD 3eed7aa. In src/, only `src/ai_checkpoint/eval/pipeline.py` changed. It gains the new helpers `_validated_unredacted` and `_validated_dict`, and the bundle branch of `_workspace_capture` now uses them. The other changes are new tests in `tests/test_eval_bundle.py`, plus the build log and the QA report.

## F-006 Eval support for the bundle path (offline)
| Criterion | Result | Evidence |
|---|---|---|
| 1. compaction_system_prompt() describes the new fields from the same schema source as the MCP tool (a test asserts this) | met | `test_prompt_contains_new_tool_field_descriptions` passed. The fix does not touch schema.py or server.py, so the direct check from attempt 1 still holds. |
| 2. Bundle path (temp store save, then resume); save-check errors are recorded, not raised | met | `test_handover_goes_through_a_bundle_store` and `test_still_rejected_after_retry_is_recorded_not_raised` passed. In my retry reproductions, a first attempt rejected for `chat_name: "a/b"` was recorded with `retry_needed: true` and status ok, and nothing was raised. |
| Ruling 1: one retry with the errors, recorded in results.json | met | `test_rejected_save_gets_one_retry_with_errors_and_is_recorded` and `test_results_json_records_whether_retry_was_needed` passed. Leakage is scored on the attempt that was saved. A leaky invalid first attempt followed by a clean retry gives leak 0. A clean invalid first attempt followed by a leaky retry gives leak 1. |
| 3. FakeModel uses the new fields and passes the save checks | met | `test_fake_output_uses_new_fields_and_passes_save_checks` and `test_fake_passes_checks_on_every_v2_scenario` (6 cases) passed. models.py is unchanged. |
| 4. `checkpoint-eval suite datasets/handover-v2/*.json --model fake --out <tmp>` works offline | met | Run with ANTHROPIC_API_KEY and OPENAI_API_KEY unset, under `sandbox-exec -p '(version 1)(allow default)(deny network*)'`. I first confirmed the sandbox blocks a socket connect (`PermissionError: [Errno 1] Operation not permitted`). Result: rc=0, 6 scenario folders, 12 results.json/results.md files. The checkpoint status is ok for all 6, secret_leakage is 0, and retry_needed is false. |
| 5. Old-format path available; existing eval tests pass | met | The same sandboxed run with `--handover-format old` gave rc=0 and 12 files. `test_old_format_flag_keeps_flat_path` passed, and the existing eval tests are among the 409. |
| 6. eval-runs/README.md documents a real v2 run; the real target is a separate manual run | met | `test_eval_runs_readme_documents_v2_run` passed. The README is unchanged. |

### Leakage reproductions
Setup: a leaking FakeModel subclass on coding-20, with `sk-fake-0123…` added to `secret_values`. Each cell is secret_leakage.

| Placement | HEAD bundle | HEAD old | BASE 31c7ac4 bundle | pre-F-006 3a9e257 |
|---|---|---|---|---|
| context | 1 | 1 | 1 | 1 |
| decisions | 1 | 1 | 1 | 1 |
| verbatim | 1 | 1 | 1 | 1 |
| env var `API_KEY=<secret>` | **0** | 0 | 1 | 0 |
| unknown top-level key | **0** | 0 | 1 | 0 |
| user_turns | 1 | 0 (no such field) | 1 | 0 |
| retry: leaky+invalid, then clean | 0 | n/a (old mode has no retry) | 0 | n/a |
| retry: clean+invalid, then leaky | 1 | n/a | 1 | n/a |

Further placements:
- Fields both modes keep give the same number in both modes: superseded decision 1/1, open_questions 1/1, next_steps 1/1, env var whose name is only the secret 1/1, checkpoint_name 1/1, chat_name 1/1, task text 1/1, workspace file path 1/1.
- A task's extra key and a task's client id give 0/0, because validation drops both.
- facts gives 1 in bundle and 0 in old. Like user_turns, only the bundle format keeps facts, so this difference is by design. The build log names user_turns as a by-design difference but does not mention facts.

At HEAD, every case where old mode reports 0 and the product never stores the secret now also reports 0 in bundle mode. That was the attempt-2 failure, and it is fixed.

### Does the helper match what store.save keeps?
Method: for each placement, I compared the helper's scoring blob with a real `GitStore.save` into a temp dir. During that save I set `store.redact_obj` to identity, then scanned every stored file and `store.get` for the secret.

The two agree on every placement except one.

**Mismatch: `next_steps` given together with `tasks`.** The helper counts the secret. store.save discards the model's next_steps because it sets `cp.next_steps = next_steps_from_tasks(...)` after validation, so the secret is never stored, even unredacted. The helper reruns `Checkpoint.from_dict` and `structured.build` but not that override, so its docstring ("The checkpoint store.save() builds from parsed") is slightly too strong.

I do not count this as a failure:
- No criterion covers this.
- The number equals old mode (1) and pre-F-006 (1).
- BASE also gave 1, so nothing regressed.
- FakeModel does not emit next_steps, so offline results are unaffected.

I record it for the orchestrator. A real model that writes both `tasks` and a next_steps entry like "export KEY=sk-…" gets a leak counted in bundle mode for a secret the bundle would not store.

The other step the helper skips (in non-carry saves, filtering the flat decisions to active ones) makes no difference, because v2 decisions keep superseded rows in the stored bundle anyway.

Side effects:
- The helper writes nothing. Neither `structured.py` nor `model.py` does any file I/O, uses globals or caches, or reads the environment.
- It does not mutate the parsed dict. I compared a deepcopy before and after for all 13 placements and found no change.
- It does not patch any store globals.
- No `aic-eval-*` temp dirs were left behind.
- Save-time validation is not content-sensitive in a way redaction could change. There are no length limits, and the helper only runs on attempts that were saved. None of the extra placements made the helper raise.

### The new tests fail on 31c7ac4 as claimed
I copied HEAD's `tests/test_eval_bundle.py` into a 31c7ac4 worktree and ran `-k secret` with that worktree's src, confirming `ai_checkpoint.__file__` pointed there. Result: `test_secret_never_stored_is_not_leakage_in_either_mode[env_var_value]` and `[unknown_key]` failed with `assert 1 == 0`, and the other 5 passed. This matches the build log.

Other checks, beyond the leakage placements:
- An invalid `last_exchange` string is rejected the same way in both modes. It is recorded as failed and nothing is raised.

## Regression sweep
BASE 31c7ac4 compared with HEAD 3eed7aa. The only touched code path is the bundle branch of `_workspace_capture`, the secret_leakage source, plus the new helpers. The old-mode branch is functionally unchanged; it was only restructured.

- **Full offline suite.** I ran the fake model on all 6 handover-v2 scenarios in both `bundle` and `old` modes, at HEAD and at BASE (BASE from a worktree with its own src). `diff -rq` of the outputs found no differences in either mode, so all other scores are unchanged.
- **Leaking placements, BASE bundle compared with HEAD bundle.** Only the env var value, the unknown key, the task extra key and the task client id changed (1 → 0). In all four the product never stores the secret, and HEAD now matches old mode and pre-F-006. The fix was meant to make these changes. All other placements, and both retry cases, are unchanged.
- **Old mode.** Identical at BASE and HEAD for every placement.

No unrequired differences were found. The worktrees for 31c7ac4 and 3a9e257 were removed and pruned. Scratch scripts and outputs were deleted, and `git status` is clean. One file I did not create, `scratchpad/d.py` (dated 15:31, from an earlier session), was left in place.
