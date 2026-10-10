VERDICT: PASS

## Verdicts
F-005: PASS

## Test suite
`.venv/bin/python -m pytest -q` at HEAD 4697925: **402 passed**, 0 failed (102 s). The `test_metrics.py::test_product_code_unchanged` failure from the build log is gone now that the change is committed.

Re-check of F-005 only. The fix diff is BASE e14e383..4697925. F-006 was not checked.

## F-005 Carry-forward plan updates by task id from a resumed chat
| Criterion | Result | Evidence |
|---|---|---|
| 1. Brief shows each task's id (`[t-2]`) | met | `test_carry.py::test_brief_shows_task_ids` (asserts `[t-2]`, `[t-3]` in the rendered brief). Code not touched by the fix. |
| 2. plan_updates [{t-2 done}, {new task, ai}] keeps parent tasks (ids, quotes, order), t-2 done, new task gets next unused id | met | `test_plan_updates_keep_parent_tasks_and_add_new` (ids t-1..t-4, text/quote/order/from equal to parent, t-2 done, t-4 = "new task"). MCP: `test_mcp_plan_updates`. |
| 3. Unknown task id gives a validation error naming the id; nothing written | met | `test_unknown_id_and_rewording_rejected_nothing_written` (message names `t-9`, git log unchanged). |
| 4. Carry-forward only for resumed saves with non-empty tasks/plan_updates/user_turns/facts; empty list = not given; old-fields-only carries nothing; events.jsonl records resumed_from | met | Tests: `test_empty_structured_list_does_not_turn_carrying_on[user_turns/facts/plan_updates]` (store path), `test_mcp_empty_structured_lists_do_not_carry` (MCP), `test_old_only_resumed_save_carries_nothing`, `test_old_only_resumed_save_uses_only_its_own_sections`, `test_adding_user_turns_switches_carrying_on`, `test_carry_forward_of_other_sections_and_events` (carry, plus `resumed_from` in events.jsonl). The tests cover the CLI path only through store.save and test the three MCP empties together, so I also checked directly, one field at a time, on store, CLI (`ai_checkpoint.cli main save --file`) and MCP (`call_tool save_checkpoint`), using a parent with decisions/facts/workspace/verbatim/open_questions. All three paths gave identical results. `user_turns: []`, `facts: []` and `plan_updates: []` together with next_steps ["only"]: nothing carried (decisions [], open_questions [], verbatim [], workspace empty, next_steps ["only"]). `facts: []` + `user_turns: ["more"]`: carries. `plan_updates: [{t-2 done}]` + `facts: []`: carries, parent plan kept. `user_turns: null`: no carry. |
| 5. plan_updates without resumed_from gives a clear error; flat parent converted then updated | met | `test_plan_updates_errors_without_resumed_from_and_with_tasks`, `test_old_flat_parent_converted_then_updated`. Direct check on store/CLI/MCP: non-empty `plan_updates` without resumed_from gives "plan_updates needs resumed_from: pass the id of the checkpoint this chat was resumed from." `plan_updates: []` without resumed_from now saves (empty = not given; see the regression sweep). |
| 6. Next action and save echo reflect the updated plan | met | `test_plan_updates_keep_parent_tasks_and_add_new` (next_action "tune", message "Next action saved: tune. Correct?"), `test_mcp_plan_updates` (same echo over MCP). |
| 7. plan_updates depends_on has its own description (real ids from the brief, not positions); new task gets next id after the highest | met | `test_plan_updates_depends_on_text_says_real_ids` (reads the live MCP schema `PlanUpdateIn.depends_on`, which differs from `TaskIn.depends_on`), `test_dependencies_in_updates`, and t-4 in criterion 2's test. Not touched by the fix. |

`tasks: []` still gives the F-004 error. On store, CLI and MCP, a resumed save with `tasks: []` fails with "The plan has no unfinished task ... Add at least one task with status todo or in_progress". The same holds for `tasks: []` + `user_turns: ["hi"]`. Also covered by `test_empty_tasks_still_reaches_no_unfinished_task_check` (store path only).

Ruled behaviour confirmed: a resumed save with only `plan_updates: []` fails on all three paths with "next_steps: is required: give `tasks` (preferred) or `next_steps`" (decisions.md, last entry).

Extra checks (adversarial):
- `user_turns: [""]` (a non-empty list whose only turn is blank) turns carry-forward on and saves, on all paths. This matches the criterion as written ("non-empty list"), and BASE behaved the same. Note only, not a failure.
- `tasks: [{text: a}]` + `plan_updates: []`: this used to give the "Give either tasks or plan_updates" error. Now it saves with the tasks and carries (tasks is non-empty). This follows from "empty list counts as not given".

## Regression sweep
BASE e14e383 → HEAD 4697925. Code touched: `GitStore.save` in `src/ai_checkpoint/store.py`. An empty `plan_updates` is now dropped before use, and the `merge` (carry-forward) switch changed from `is not None` to `bool(...)`. `docs/DESIGN-v2.md` changed (one sentence). `tests/test_carry.py` got 3 new tests, and one existing test changed its `plan_updates: []` to `[{"text": "z"}]` (needed: an empty list no longer carries).

I ran the same 14 inputs against a BASE worktree and HEAD, through the store and MCP paths. Differences found, all required by Chirag's empty-list ruling or explicitly ruled:
- `user_turns: []` / `facts: []` + next_steps (store path): BASE carried, HEAD does not. Required by criterion 4. (MCP was already not carrying at BASE, so the paths now agree.)
- `plan_updates: []` + next_steps: BASE kept the parent plan and carried (store and MCP). HEAD uses next_steps and carries nothing. Required by criterion 4.
- `plan_updates: []` alone: BASE kept the parent plan. HEAD gives "next_steps: is required". Ruled intended by Chirag.
- `plan_updates: []` without resumed_from: BASE gave "plan_updates needs resumed_from". HEAD saves normally. Follows from "an empty list counts as not given"; disclosed in build-log. A non-empty list still errors, as criterion 5 requires.
- `tasks: [...]` + `plan_updates: []`: BASE gave "Give either tasks or plan_updates". HEAD saves with the tasks. Same reasoning.

Unchanged between BASE and HEAD: `tasks: []` (F-004 error), `tasks: []`+user_turns, `user_turns: null`, old-fields-only, mixed empty+non-empty, non-empty plan_updates with `facts: []`, `user_turns: [""]`, and non-empty plan_updates without resumed_from (error).

Worktree and scratch files removed. (A separate `scratchpad/f006/base` worktree belongs to the parallel F-006 QA and was left alone.)
