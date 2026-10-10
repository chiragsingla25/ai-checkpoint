VERDICT: FAIL

## Verdicts
F-005: FAIL

## Test suite
`$HOME/aic-venv/bin/python -m pytest -q` could not be run because `$HOME/aic-venv` does not exist on this machine (`no such file or directory`). I used the repo venv instead: `/Users/chiragshome/projects/ai-checkpoint/.venv/bin/python -m pytest -q` at HEAD 9d6883e, clean tree. Result: **381 passed** in 80.9s, 0 failed. `test_product_code_unchanged` passes now that the change is committed. The module path was confirmed as `/Users/chiragshome/projects/ai-checkpoint/src/ai_checkpoint/__init__.py`.

## F-005 Carry-forward plan updates by task id from a resumed chat
| Criterion | Result | Evidence |
|---|---|---|
| 1. Brief shows each task's id | met | `test_carry.py::test_brief_shows_task_ids` (render_brief of a real bundle, asserts `[t-2]`, `[t-3]`). Unchanged since attempt 1, where I also checked it by hand. |
| 2. resumed_from + plan_updates [{t-2 done},{new task, ai}] keeps parent tasks (ids, quotes, order), t-2 done, new task gets the next unused id | met | `test_plan_updates_keep_parent_tasks_and_add_new` (compares text/quote/order/from of t-1..t-3 against the parent's plan.json; t-2 done; new t-4). `test_mcp_plan_updates` does the same over MCP. |
| 3. Unknown id -> validation error naming the id; nothing written | met | `test_unknown_id_and_rewording_rejected_nothing_written` (message `plan_updates[1]: unknown task id t-9 (parent cp-001 has ...)`, git log unchanged). |
| 4. Carry-forward **only** for resumed saves with structured fields; an old-fields-only resumed save behaves as before (nothing carried); events line records resumed_from | **not met** | The structured part is met (`test_carry_forward_of_other_sections_and_events`, which also checks events `resumed_from`). The old-only part fails. HEAD carries the parent's sections into an old-fields-only resumed save. Direct run at HEAD: parent cp-001 with decision "Use X", fact k, user_turn, workspace /w, open_question q1. Then `save(resumed_from=cp-001, next_steps=["go on"])` -> cp-002 has `decisions ['Use X']`, `open_questions ['q1']`, workspace files `[/w]`, facts `['k']`, user_turns `['do a then b']`. The same script on 078586c (before F-005) gives `decisions [] oq [] files [] facts [] turns 0`, so this is not "as before". The tests enforce the withdrawn ruling: `test_old_only_resumed_save_carries_omitted_sections` and `test_old_only_resumed_save_supplied_sections_replace_wholesale` both pass, so they assert the opposite of criterion 4. `store.save` sets `carry = parent_v2 is not None` with the comment "Every save of a resumed chat carries ...". DESIGN-v2 §11 "When carry-forward applies" still describes the withdrawn ruling. |
| 5. plan_updates without resumed_from -> clear error; flat parent converted then updated | met | `test_plan_updates_errors_without_resumed_from_and_with_tasks`, `test_old_flat_parent_converted_then_updated` (real flat cp-001.json, t-1 done, raw kept, flat file byte-identical). |
| 6. Next action and save echo reflect the updated plan | met | `test_plan_updates_keep_parent_tasks_and_add_new` (`next_action` "tune", echo `Next action saved: tune. Correct?`), `test_mcp_plan_updates` (MCP echo). |
| 7. plan_updates depends_on has its own description (real ids from the brief, e.g. "t-2", not positions; a new task gets the next id after the highest in the brief) | met | `test_plan_updates_depends_on_text_says_real_ids` reads the live MCP input schema (`$defs.PlanUpdateIn.properties.depends_on`). It asserts the text equals the new FIELD_DESCRIPTIONS entry, differs from `tasks.depends_on`, lacks the positional sentence and contains "next id after the highest", and that TaskIn keeps the positional text. Direct dump of the schema: `Optional. Ids of tasks that must be done first. These are the real task ids shown in the brief (e.g. ["t-2"]), NOT list positions. A new task in plan_updates gets the next id after the highest one in the brief, so a dependency on another new task uses that id.` |

Extra checks (criterion 7, following the text literally; parent brief t-1..t-2):
- `[{text x}, {text y, depends_on ["t-3"]}]` -> t-3 x, t-4 y depends on t-3. This matches the description.
- Forward reference `[{text x, depends_on ["t-4"]}, {text y}]` -> accepted, t-3 depends on t-4. This is consistent.
- Self-dependency `[{text x, depends_on ["t-3"]}]` -> `ValidationError plan: dependency cycle t-3 -> t-3`. Nothing is written.
- `[{id t-2, depends_on []}]` -> accepted, deps cleared.

## Regression sweep
BASE 9107b1e -> HEAD 9d6883e. The only product-code change is the `plan_updates.depends_on` string in `src/ai_checkpoint/schema.py`, plus the test and RUN files. I compared old and new through a worktree at 9107b1e (module path confirmed) by dumping every MCP tool (`list_tools`, full model_dump) and `FIELD_DESCRIPTIONS` from both. The only differences are that one FIELD_DESCRIPTIONS entry and the identical `PlanUpdateIn.depends_on` description in the save_checkpoint schema. All other tool fields and descriptions are identical, and the SAVE_DESCRIPTION text is unchanged. No regression. The worktree was removed.

Out of scope for this diff but relevant: the criterion 4 failure was already present at BASE 9107b1e. It is not new in 9d6883e. The attempt-1 commit landed the orchestrator's "carry for every resumed save" behaviour, which Chirag's ruling later withdrew. My attempt-1 report described the earlier working tree, where old-only resumed saves carried nothing.

## Notes
1. **Repo `.venv` / pytest install:** `.venv/` is ignored (`.gitignore:7: .venv/`). pytest 9.1.1 is installed only inside `.venv` and matches the `dev = ["pytest"]` extra in pyproject.toml. `git status --porcelain` is empty. No venv, egg-info or cache files are tracked (`git ls-files` finds none). The ignored entries are `.venv/`, `.pytest_cache/`, `src/ai_checkpoint.egg-info/`, `__pycache__/` dirs, `.DS_Store`, `.env.local` and `results/`. Nothing needs action. The documented test command `$HOME/aic-venv/bin/python` does not exist here. The build log for attempt 2 already uses `.venv/bin/python`, so the run's "how to run" line should be updated to that.
2. decisions.md (Chirag's ruling) says "The builder's attempt 1 already implements (a), so no code change is needed". That is not true of the committed code (see criterion 4), and neither is the attempt-2 build log's "criterion 4 stays option (a)".
3. Commit 9107b1e (attempt 1, not this diff) also deleted tracked `.DS_Store` files and added two `.gitignore` lines. That is harmless, and I am recording it only for visibility.

## For the builder (failing features only)
**F-005, criterion 4: old-fields-only resumed saves must carry nothing.**
- Reproduce: save a structured parent with decisions, facts, user_turns, workspace and open_questions. Then `store.save({chat_name, checkpoint_name, objective, current_step, resumed_from: <parent>, next_steps: ["go on"]})`. The result currently contains the parent's decisions, facts, user_turns, workspace, open_questions and verbatim.
- Correct: the result is identical to what 078586c produced, with nothing from the parent carried (decisions, facts, user_turns, workspace, open_questions and verbatim are only what the save supplied). Task ids still continue from the lineage max, as before. Carry and merge apply only when the save gives `tasks`, `plan_updates`, `user_turns` or `facts`. The events line still records `resumed_from`.
- Where: `store.save` (`carry = parent_v2 is not None`, plus the comment above it), and the `replace=not merge` / `_carry_flat` old-only branch, which becomes dead code. Tests `test_old_only_resumed_save_carries_omitted_sections` and `test_old_only_resumed_save_supplied_sections_replace_wholesale` assert the withdrawn ruling and must be changed to assert that nothing is carried and the output matches pre-F-005. DESIGN-v2 §11 "When carry-forward applies" must be reworded to option (a).
