VERDICT: OBJECTION

12 of 13 criteria met as written. The one not met is "Full suite passes". That criterion cannot be met in the state F-001 is checked in, uncommitted, because an existing guard test fails whenever schema.py is modified. The suite passes 308/308 once the change is committed (simulated in a scratch copy). See Objection.

| Criterion | Result | Evidence |
|---|---|---|
| Rule 1 user's plan first | met | `SAVE_INSTRUCTIONS` contains "user's own words", "in order" and "`next_steps`" (all True via `qa_chk.py`). The amended bullet says `next_steps` must START with the plan, every part, in order, then own steps. |
| Rule 1 identifiable marker | met | The bullet contains `the exact text "User's plan:"`. `FIELD_DESCRIPTIONS["next_steps"]` = "...If the user stated their own plan, it comes first, in their words and in order, each step starting with \"User's plan:\"; your own steps come after." brief.py is unchanged. Rendered brief shows `1. User's plan: write the migration` ... `4. Run the full suite`. MCP save to resume shows 3 `User's plan:` lines in the brief. |
| Rule 2 done-with listed | met | "done_with", "full path", "rename", "env var" and "never their values" are all present. `FIELD_DESCRIPTIONS["workspace"]` adds "but done-with items must be listed too, not dropped." |
| Rule 2 checklist unchanged | met | `git diff --stat src/ai_checkpoint/brief.py` is empty. Test checkpoint with done_with folder `/Users/c/proj/old_abandoned_dir`, env var `OLD_TOKEN_NAME`, connector Slack, plus still_relevant `DATABASE_URL` and `app.py`. 'Set up first' lists only DATABASE_URL and app.py. Same brief sha (3409ce6648df) under old and new code. Edge case: all items done_with gives no 'Set up first' section in either version. |
| Rule 3 rejected always filled | met | The bullet contains "For EVERY decision where alternatives were discussed ... even when the reason is short or the option was only mentioned". `decisions.rejected` no longer starts with "Optional."; it now starts "`rejected` must hold every alternative discussed for this decision, even when the reason is short; empty only if none came up." |
| Wording stays short | met | SAVE_DESCRIPTION 2279 -> 2829 bytes (+550, limit ~900). Bullet count is 9 old and 9 new, so the three rules are amendments to existing bullets. |
| Compaction prompt carries rules | met | `SAVE_INSTRUCTIONS in compaction_system_prompt()` is True. The three updated FIELD_DESCRIPTIONS texts are in the prompt (True). New `test_save_instructions_carry_the_three_rules` asserts "User's plan:", "full path" and "EVERY decision" in the prompt and passes. The existing compaction-prompt test passes. |
| MCP tool description updated | met | `create_server().list_tools()` save_checkpoint description == SAVE_DESCRIPTION (True). The JSON-escaped field descriptions for next_steps, workspace and decisions.rejected are found in `input_schema`. Tools are the same 4. The parameter list is identical (15 props). Input schema with descriptions stripped has the same sha (56842f558fd0) old and new. |
| Pinned hash tests updated | met | tests/test_eval.py has sha 3d9a427f..., len 2829, plus a comment giving the previous 0b89d3ba.../2279 and the eval-runs/2026-10-09-handover-v2-haiku reason. The paragraph-break assertion is updated to `do not write "User's plan:".\n\nPick a short, descriptive` and passes. Independently recomputed: len 2829, sha 3d9a427f. |
| No format/store/tool change | met | `git diff --stat` touches only src/ai_checkpoint/schema.py and tests/test_eval.py. The model/store/brief diff is empty. COMPACTION_FIELDS repr sha is ff3a16a91f0f in both old and new. |
| Old checkpoints unchanged | met | `pytest tests/test_rejected.py` passes (store, MCP resume and CLI golden tests). Direct `render_brief(old_format_cp) == golden` is True under both versions. `git status --short tests/fixtures` is empty. |
| FakeModel compaction validates | met | 12 dataset scenarios compacted with FakeModel under the new `compaction_system_prompt()` all pass `Checkpoint.from_dict`. Output sha (f97f23baff2d) is identical to old code. `test_fake_compaction_workspace_validates...`, test_eval, test_runner and test_retry pass (95 passed in the targeted run). |
| Full suite passes | not met as written | `$HOME/aic-venv/bin/python -m pytest -q` in the working tree: `1 failed, 307 passed`. The failure is `tests/test_metrics.py::test_product_code_unchanged` with `AssertionError: ['src/ai_checkpoint/schema.py']`. In a scratch copy with the change committed (`git commit -qam sim`, PYTHONPATH pointed at the copy, `ai_checkpoint.__file__` confirmed): `308 passed`. |

## Extra checks
- MCP save to resume round trip in a temp store, with User's plan steps, a rejected option and a done_with folder plus env var. Save succeeds. The brief shows the 3 User's plan lines and no 'Set up first' section (all items done_with). `get_checkpoint` still holds the done_with items.
- Reading the new text as a reader. It is clear and short, and I found no hard contradiction:
  - "Leave `rejected` empty only if no alternative came up" agrees with "Do not leave a section empty if the conversation has anything for it".
  - "even when ... the option was only mentioned" stays within "Never invent": it covers things actually said.
  - "an env var NAME that was used" agrees with names-only and no-values.
  - "If the user gave no plan, do not write 'User's plan:'" guards against made-up plans.
- Minor reader notes (not failures):
  1. "the user's own words" sits next to "concrete instructions the next AI can follow without asking". A loose user plan stays in the user's wording. That is the intent, since added steps come after, but a saver may hesitate.
  2. It does not say whether a single-sentence plan ("X, then Y, then Z") should become one step or three. "each step beginning" implies splitting.
  3. FIELD_DESCRIPTIONS next_steps says "in their words and in order" but not "every part", which SAVE_INSTRUCTIONS says.
  4. The pre-existing `decisions.reason` text ("including options that were rejected") overlaps with `rejected`. It is unchanged and harmless.
- Design note: done_with items never appear in the resume brief, only in the stored checkpoint JSON via get_checkpoint. That is by design (brief layout unchanged). Gap (2) improves only for consumers that read the JSON or workspace. Worth keeping in mind when reading the Haiku re-run.
- The new test checks "full path" in the prompt but not "done_with" by name. done_with is in the prompt anyway (verified).

## Regression sweep
- Touched: `SAVE_INSTRUCTIONS` (hence `SAVE_DESCRIPTION`, the MCP tool description and `compaction_system_prompt()`) and `FIELD_DESCRIPTIONS` next_steps, workspace and decisions.rejected (MCP input_schema descriptions and the compaction prompt).
- Old code from `git archive HEAD` to `$HOME/qa-old`, confirmed via `ai_checkpoint.__file__`. Compared old against new:

| What was compared | Old | New | Result |
|---|---|---|---|
| Old-format fixture brief | equals golden | equals golden | same |
| New-style checkpoint brief (user plan + done_with) | sha 3409ce6648df | sha 3409ce6648df | same |
| All-done_with workspace brief | no 'Set up first' | no 'Set up first' | same |
| FakeModel compaction over 12 scenarios | sha f97f23baff2d | sha f97f23baff2d | same |
| MCP tool list | 4 tools | 4 tools | same |
| save_checkpoint parameters | 15 | 15 | same |
| Input schema minus descriptions | 56842f558fd0 | 56842f558fd0 | same |
| COMPACTION_FIELDS | ff3a16a91f0f | ff3a16a91f0f | same |
| SAVE_DESCRIPTION / field descriptions | old text | new text | differ, as required |

- No regression found.

## Objection (OBJECTION only)
- Criterion: "Full suite passes: `$HOME/aic-venv/bin/python -m pytest -q` reports all tests passing (baseline 307 passed; count may only increase)."
- Why it cannot be met as written: `tests/test_metrics.py::test_product_code_unchanged` asserts `git status --porcelain -- src/ai_checkpoint` is clean outside `eval/`. It is a guard from an earlier eval-only run. This feature is required to modify src/ai_checkpoint/schema.py, and QA checks it before the orchestrator commits. So in the checked state the suite is necessarily `307 passed, 1 failed`, whatever the builder does. The builder could only "fix" it by committing (not their role) or by weakening the guard (out of scope).
- Evidence: working tree gives `1 failed, 307 passed`, and the only failure is that guard naming schema.py. A committed scratch copy gives `308 passed`. Every other test passes, including the new one.
- Proposed wording: "Full suite passes: `pytest -q` reports all tests passing (baseline 307; count may only increase), except `tests/test_metrics.py::test_product_code_unchanged`, which is expected to fail only while src/ai_checkpoint/schema.py is uncommitted. It must pass, with the whole suite green, after the orchestrator commits F-001."
- If the owner accepts that wording, this attempt meets all 13 criteria and should be recorded as PASS without rework. The guard test could also be retired or scoped to eval-only runs in a later change.
