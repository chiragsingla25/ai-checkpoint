VERDICT: PASS

All 7 of 7 criteria are met through both `GitStore.save` and the MCP `save_checkpoint` tool. The attempt-2 gap is fixed: an explicit `tasks: []` now reaches check 3 through MCP and gets the "no unfinished task" error with isError True, and nothing is written. A normal MCP save with tasks, and an old-fields-only MCP save, give byte-identical results to HEAD (commit hash masked). The only schema change is that `tasks` became nullable with default null.

Environment: new = working tree (module path confirmed `$HOME/mnt/ai-checkpoint/src/ai_checkpoint/__init__.py`). Old = HEAD 5366c3a via `git archive` into `$HOME/qa-old`, run with `PYTHONPATH=$HOME/qa-old/src` (module path confirmed `$HOME/qa-old/src/ai_checkpoint/__init__.py`; the stdio server subprocess inherits the same PYTHONPATH). Stores only under `$HOME/qa-tmp`. Scripts: `mcp3.py` (a real stdio MCP session via the tests' `_run_stdio`: list_tools schema, 15 save cases, get and resume), and `st3.py` (the same 15 cases plus 3 more through GitStore, each with a before/after check of commit count, file count and events.jsonl size).

Test suite: `python -m pytest -q` -> `1 failed, 365 passed`. The one failure is `test_metrics.py::test_product_code_unchanged`, the known check on uncommitted product code, so I did not count it. Attempt 3 added the in-process MCP test for `tasks: []`.

| Criterion | Result | Evidence (Store / MCP) |
|---|---|---|
| 1. Unmatched quote rejected, error names task and quote, nothing written | met | Both: `"run the back-test on 2024 data"` vs user turn `"First, run the BACK-TEST on 2023 data; then write the report!"` -> `Save rejected: 1 problem found. Nothing was saved. ... 1. Task t-1 is from=user but its quote was not found in user_turns or last_exchange.user: "run the back-test on 2024 data". ...` (MCP isError True). Store: `unchanged=True` for every rejection, and the next save is cp-009, the next id in sequence. MCP store: 7 commits for 7 successful saves and only cp-001..cp-007 on disk, so the 8 rejected calls wrote nothing. A quote spanning two turns is rejected. A quote matching only last_exchange.user is accepted on both paths. |
| 2. Case/whitespace/punctuation tolerated, changed word not; test pins both | met | Both: `“RUN the back—test, on 2023 DATA…”` accepted; changed word rejected. `test_quote_matching_tolerates_case_space_punct_not_words` pins the accepted and rejected variants. |
| 3. All done or empty -> error saying an unfinished task is needed | met | Both: all done -> `1. The plan has no unfinished task (every task is done, or there are no tasks). Add at least one task with status todo or in_progress ...`. **`tasks: []`** -> the same text on both paths (MCP isError True). Store: also with `resumed_from`. `tasks: [] + next_steps: ["x"]` -> saved on both paths (unchanged from HEAD). |
| 4. No reason heuristic; empty rejected accepted; carried-forward items not rechecked | met | Store: a decision with empty `rejected` -> saved (cp-008). Parent with that decision, then resumed old-only (cp-002) and resumed structured (cp-003) saves both pass. MCP: `old only+decisions` with empty rejected -> saved, identical to HEAD. |
| 5. All failures together; MCP error readable | met | Both: `Save rejected: 4 problems found. ... 1. ... "never said [REDACTED]" ... 2. ... has no quote ... 3. ... "made up" ... 4. The plan has no unfinished task ...`. MCP isError True, plain text. |
| 6. Valid save passes; old-only not rejected by new checks | met | Both: normal tasks save, old-only `["User's plan: do x","ai step"]`, and old-only with decisions all saved. Documented in DESIGN §8 "Which checks apply". |
| 7. Secrets redacted before the check; equal redaction passes | met | Both: a GitHub token in quote and turn -> accepted. A rejected quote echoes `[REDACTED]`. grep finds no `ghp_abc` anywhere in either store or in the stdio home. |

## Regression: MCP tool vs HEAD (stdio, same 15 calls on both)
- **Identical** (commit hash masked): normal tasks save, old-only, old-only with decisions, `tasks: [] + next_steps`, no plan field, `tasks: "x"` (pydantic list_type error), task item without text (pydantic missing error), and `resume_checkpoint cp-002` (timestamp masked).
- **get_checkpoint cp-001**: identical except `manifest.files["brief.md"]` sha256. The brief embeds the save timestamp, which differs between runs. The resume text, compared with the timestamp masked, is identical.
- **Intended differences:** all done, changed word, multiple failures and `tasks: []` are now rejected by checks 1–3 as required. Successful saves after those cases get lower cp numbers, because the rejected calls no longer use up a save.
- **`tasks: null` (explicit):** HEAD gave pydantic `tasks: Input should be a valid list [type=list_type, input_value=None]`. Now it is treated as absent: `next_steps: is required: give \`tasks\` (preferred) or \`next_steps\`` (with next_steps it would save). This is a direct result of the nullable schema. It is more lenient and gives a clearer message, so I don't count it as a regression.
- **Tool input schema:** same property set, same `required` (`chat_name, checkpoint_name, objective, current_step`), same `$defs`. Only `tasks` changed: `{"type":"array","items":{$ref TaskIn}}` became `{"anyOf":[{"type":"array","items":{$ref TaskIn}},{"type":"null"}],"default":null}`. Its description is the F-004 attempt-1 rewording ("numbers them for you; in depends_on, task k of your list is t-k"). The schema grew from 13148 to 13211 chars. SAVE_DESCRIPTION is unchanged, and its pinned-hash tests pass.

## Store path vs attempt 2
Attempt 3 did not touch the store code. All store cases give the same results as in my attempt-2 run. `tasks: "x"` through the store still gives `next_steps: is required ...` (a note from attempt 2; MCP rejects it earlier with a pydantic list_type error).

## Notes (not failure causes; carried forward)
1. A dropped apostrophe is rejected (`"Let's ship it"` vs quote `"lets ship it"`). This follows DESIGN §8, but small models often drop apostrophes.
2. Different secrets match after redaction (both become `[REDACTED]`). This is inherent to redact-then-compare.
3. A resumed save that repeats a parent user task without user_turns is rejected until F-005 carries user_turns forward. F-005 QA should check this case.
4. Some clients send `null` for optional arrays; with the nullable `tasks` that is now handled the same as an absent field, which is a small plus.

Scratch dirs `$HOME/qa-tmp` and `$HOME/qa-old` were removed after the run.
