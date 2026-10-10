VERDICT: PASS

## Verdicts
F-005: PASS

## Test suite
I ran `.venv/bin/python -m pytest -q` once at HEAD 3a9e257 on a clean tree. It gave **1 failed, 381 passed** in 344.6s. The failure was `tests/test_setup_script.py::test_full_flow`, which runs the setup script end to end: it creates a venv and pip-installs into it. I re-ran that one test on its own (`.venv/bin/python -m pytest -q tests/test_setup_script.py::test_full_flow`) and it passed (1 passed in 78.5s). Two things make it look environmental. First, it is a slow end-to-end install that ran at the same time as my worktree comparison scripts. Second, BASE..HEAD does not touch the setup script or anything it installs. I did not re-run the whole suite. All `tests/test_carry.py` tests passed, including the rewritten ones: `test_old_only_resumed_save_carries_nothing`, `test_old_only_resumed_save_uses_only_its_own_sections` and `test_adding_user_turns_switches_carrying_on`.

## F-005 Carry-forward plan updates by task id from a resumed chat
| Criterion | Result | Evidence |
|---|---|---|
| 1. Brief shows each task's id | met | `test_brief_shows_task_ids` passed. It is unchanged since attempt 2. The HEAD briefs from my direct runs also show `**[t-4]** only this` / `- [t-4] (todo) only this`. |
| 2. resumed_from + plan_updates [{t-2 done},{new task, ai}] keeps parent tasks (ids, quotes, order), t-2 done, new task gets the next unused id | met | `test_plan_updates_keep_parent_tasks_and_add_new` and `test_mcp_plan_updates` passed. Both are unchanged and were reviewed in attempt 2. |
| 3. Unknown id -> validation error naming the id; nothing written | met | `test_unknown_id_and_rewording_rejected_nothing_written` passed. It is unchanged and asserts `unknown task id t-9 (parent cp-001 has ...)` with the git log unchanged. |
| 4. Carry only for resumed saves with structured fields; an old-fields-only resumed save behaves as before; events records resumed_from | met | **Old-only = before:** see the direct comparison below. HEAD output is identical to 078586c (pre-F-005) across 8 scenarios. **Structured fields switch carrying on:** I checked each of the four fields directly (below) and via `test_adding_user_turns_switches_carrying_on` and `test_carry_forward_of_other_sections_and_events`. **events.jsonl:** the HEAD line for every resumed save I made contains `"resumed_from":"cp-001"`, e.g. `{"seq":2,...,"type":"checkpoint_saved","checkpoint_id":"cp-002","checkpoint_name":"c2","resumed_from":"cp-001",...,"next_action":"t-4",...}`. That covers both old-only and structured saves, through the store and through MCP. |
| 5. plan_updates without resumed_from -> clear error; flat parent converted then updated | met | `test_plan_updates_errors_without_resumed_from_and_with_tasks` and `test_old_flat_parent_converted_then_updated` passed. Both are unchanged. |
| 6. Next action and save echo reflect the updated plan | met | `test_plan_updates_keep_parent_tasks_and_add_new` and `test_mcp_plan_updates` passed. Direct check at HEAD: plan_updates `[{id t-2, done}]` gives plan t-1 done, t-2 done, t-3 todo and message `Saved as 'c2'. Next action saved: tune. Correct?`. |
| 7. plan_updates depends_on has its own description (real ids, not positions; next id after the highest) | met | `test_plan_updates_depends_on_text_says_real_ids` passed. `schema.py` and `server.py` are unchanged in BASE..HEAD. |

**Criterion 4: old-only resumed save, HEAD vs 078586c (pre-F-005).** I set up worktrees at 078586c and 9d6883e and confirmed the module path for each one (`.../wt-pre/src/ai_checkpoint/__init__.py`, `.../wt-base/...`, and the repo `src/...` for HEAD). The same script ran on each. It saves a parent, then an old-fields-only child with `resumed_from=cp-001`. For each run it captures `SaveResult.to_dict()` (including the save message and next_action), `store.get(cid).to_dict()` (the flat view, without v2), and the text of every bundle file (core.json, plan.json, decisions/facts/user_turns jsonl, workspace.json, open_questions.json, verbatim/*, brief.md, manifest.json). Timestamps were normalised. There were two parents: the structured parent from test_carry (tasks, user_turns, decision, fact, workspace /data/a, verbatim, open question), and an old-fields parent (next_steps, decision, workspace /w, verbatim, open question). There were four children per parent:
- A `next_steps:["only this"]`
- B `next_steps` + `decisions` (restating "Use Prophet" + "Weekly") + `workspace` /data/z + `open_questions:["new q"]` + `verbatim`
- C `next_steps:["z"]` + `context`
- D `next_steps:["z"]` + `decisions:[]`, `open_questions:[]`, `verbatim:[]`

Result: **pre-F-005 and HEAD are identical in all 8 scenarios** once the commit sha and the brief.md hash in the manifest are normalised. Both depend only on the timestamp, and the normalised brief.md text is identical. That includes the message (e.g. `Saved as 'c2'. Next action saved: only this. Correct?`, next_action `t-4` after a 3-task parent and `t-3` after a 2-step flat parent), the flat get() and every bundle file. Example B at HEAD: decisions are exactly `Use Prophet (still)`, `Weekly`, with no duplicate and no parent carry. Workspace is only /data/z, open_questions is `["new q"]`, verbatim is `nn`, and facts and user_turns are empty. BASE 9d6883e differs from both, as expected: it carried the parent's sections.

**Criterion 4: structured fields switch carrying on (HEAD, direct, structured parent).** In every case below the parent's decision `Use Prophet`, fact `freq`, open question, verbatim `make go` and workspace `/data/a` are all present in the child.
- `next_steps` + `user_turns:["More please."]`: carried, turns=2.
- `next_steps` + `facts:[{k2}]`: carried, facts `['freq','k2']`.
- `tasks:[{n}]`: carried, plan `t-4 n`.
- `plan_updates:[{t-2 done}]`: carried, plan t-1..t-3 with t-2 done.
- Over MCP, `next_steps` + `user_turns`: carried, turns=2.

Over MCP, an old-only save (`next_steps` only, and also with explicit `user_turns:[]`, `facts:[]`) carries nothing.

Extra checks:
- **Empty structured lists through the Python/CLI path (observation, not a failure).** `store.save({..., resumed_from, next_steps:["n"], user_turns: []})`, and the same with `facts: []`, **does** carry everything from the parent at HEAD, because `merge` tests `is not None`. Pre-F-005 would carry nothing. MCP drops empty `user_turns`/`facts` (`server.py:217-220`), so MCP saves are not affected. The CLI (`cli.py save`) passes the JSON through unchanged, so a JSON file with `"user_turns": []` would carry. The criterion says "gives structured fields". An empty list arguably gives the field, so I do not count this against the criterion. The orchestrator may want to decide whether an empty list should count as "not given", which is what DESIGN-v2 §11 already says for `decisions`.
- A resumed save with no `next_steps`/`tasks` (and one with `next_steps: []`) fails with `ValidationError('next_steps: is required: give `tasks` (preferred) or `next_steps`')`. The behaviour is identical pre-F-005 and at HEAD.

## Regression sweep
BASE 9d6883e to HEAD 3a9e257. Product code touched:
- `store.GitStore.save`: `carry = parent_v2 is not None and merge`, and the call to `structured.build` no longer passes `replace`.
- `store.GitStore._carry_flat`: the `merge` parameter and the old-only replace/carry branch were removed.
- `structured.build`: the `replace` parameter was removed. `parent` decisions are now always copied when `parent` is given.

`docs/DESIGN-v2.md` §11 was reworded to option (a). Tests changed as shown in the diff.

`replace` removal: `grep` finds no remaining caller passing `replace=` and only one `structured.build(` call site (`store.py:323`), so nothing breaks. With `replace` gone, `build(parent=...)` is now only reached when `merge` is true, which is the case where `replace` was already False. The removed branch was reachable only for old-only carrying saves, which criterion 4 now requires to carry nothing.

Old vs new, through the 9d6883e worktree and HEAD using the same script with every 64/40-hex hash normalised. Inputs were structured resumed saves, each against both a structured parent and an old-fields parent:
- `user_turns` + `decisions` with `supersedes:"d-1"` + `workspace` (update of /data/a to done_with, add /data/z) + `open_questions:[]` + `verbatim`
- `facts` (freq superseded)
- `tasks` + a restated decision
- `plan_updates` (t-2 done, new task depending on t-2) + `workspace.commands`
- non-resumed old-fields save
- non-resumed structured save

Result: **identical in all 12 scenarios**, covering the result, the message, get() and every bundle file. The facts.jsonl hash differs only because of its `valid_from` timestamp, and the normalised text is equal. The only behaviour change in BASE..HEAD is the old-only resumed save, and criterion 4 requires it (shown above to now match 078586c). No regression.

I removed both worktrees (`git worktree list` shows only the main tree) and the scratch scripts and outputs. `git status --porcelain` is clean. I could not delete the temporary stores that my scripts created with `tempfile.mkdtemp()`: about 97 `tmp*/s` folders under `/var/folders/py/t_6jybfj24n0dt6nw2nzf8840000gn/T`. A safety check blocked the removal, so they are left for the user or the OS temp cleanup.

## Notes
1. `test_setup_script.py::test_full_flow` failed once in the full run and passed on its own (see Test suite). It is unrelated to this diff, but it may be flaky under load or network conditions.
2. Empty `user_turns`/`facts` lists through store.save or the CLI switch carrying on, while the same save over MCP does not. See Extra checks. This is for the orchestrator to decide whether to raise it. It does not affect this verdict.
