VERDICT: FAIL

6 of 7 criteria are met. The attempt-1 gap is fixed only in `GitStore.save`, not in the MCP tool. `store.save({..., "tasks": []})` now gives the check-3 "no unfinished task" CheckError. But the MCP `save_checkpoint` tool, the surface the chat model actually calls, still returns `next_steps: is required: give \`tasks\` (preferred) or \`next_steps\`` for `tasks: []`. `server.py` declares `tasks: List[TaskIn] = Field(default_factory=list)` and forwards it only `if tasks:`, so an explicit empty list is dropped before the store sees it. My attempt-1 report gave the MCP path as a reproduction. Everything else still holds, and every adversarial case behaves as it did in attempt 1.

Environment: new = working tree (module path confirmed `$HOME/mnt/ai-checkpoint/src/ai_checkpoint/__init__.py`). Old = HEAD 5366c3a via `git archive` into `$HOME/qa-old` (module path confirmed). Stores only under `$HOME/qa-tmp`. Scripts: `p4.py` (34 store cases, each with a before/after check of commit count, file count and events.jsonl size), `s4.py` (a real stdio MCP session via the tests' `_run_stdio`), `m4.py` (decision/resume cases).

Test suite: `python -m pytest -q` -> `1 failed, 364 passed`. The one failure is `test_metrics.py::test_product_code_unchanged`, the known check on uncommitted code, so I did not count it. The new test `test_empty_tasks_gets_unfinished_task_error_nothing_written` covers the store only.

| Criterion | Result | Evidence |
|---|---|---|
| 1. Quote not in user_turns / last_exchange.user -> rejected naming task and quote; nothing written | met | `"run the back-test on 2024 data"` vs user turn `"First, run the BACK-TEST on 2023 data; then write the report!"` -> `1. Task t-1 is from=user but its quote was not found in user_turns or last_exchange.user: "run the back-test on 2024 data". ...`. `unchanged: True` for every rejection. The next save after all the rejections is cp-015, the next id in sequence. Also rejected: no evidence, a quote spanning two turns, a partial word, `"..."`. Quote matching only last_exchange.user -> accepted (store cp-005; MCP `ship IT` vs `Ship it.` -> isError False). |
| 2. Case/whitespace/punctuation tolerated, changed words not; test pins both | met | Accepted: `"first   run the back test on 2023 data."`, and curly quotes / em dash / ellipsis. Rejected: changed word, dropped word. `test_quote_matching_tolerates_case_space_punct_not_words` pins both, plus a word-boundary case. |
| 3. All done **or empty** -> error saying at least one unfinished task is needed | **not met (MCP)** | Store: all done -> check-3 message. `tasks: []` -> `Save rejected: 1 problem found. ... 1. The plan has no unfinished task ...`, and the same for `tasks: [] + next_steps: []`, `tasks: []` with resumed_from, and `tasks: []` with a secret in objective. Nothing written in any of them. `tasks: [] + next_steps: ["a"]` -> saved (correct). **MCP stdio:** `call_tool("save_checkpoint", {..., "tasks": []})` -> `isError= True \| Error executing tool save_checkpoint: next_steps: is required: give \`tasks\` (preferred) or \`next_steps\``. |
| 4. No reason heuristic; empty rejected accepted; carried-forward items not rechecked | met | A decision with empty `rejected` and a reason naming alternatives -> saved. Parent with that decision, then a resumed old-only save (cp-002) and a resumed structured save (cp-003) both pass. |
| 5. All failures together; MCP error result readable | met | stdio MCP: `isError= True`, `Save rejected: 4 problems found. ... 1. ... "I never said [REDACTED]" ... 2. Task t-2 ... has no quote ... 3. ... "made up" ... 4. The plan has no unfinished task ...`. Store: the same 4-problem case. |
| 6. Valid save passes; old-only saves not rejected by new-field checks | met | Valid structured saves cp-002..cp-012. Old-only `["User's plan: invented by model","ai step"]` -> saved, also with unrelated user_turns. Documented in DESIGN §8 "Which checks apply". |
| 7. Secrets redacted before quote check; equal redaction passes | met | GitHub token / `password=` / sk-ant key on both sides (user_turns or last_exchange) -> accepted. A rejected quote echoes `[REDACTED]`. grep finds no secret in any store or in the stdio home. |

## Extra checks
- Secret in a field of a `tasks: []` save (objective) -> CheckError; the secret is not echoed or written.
- `tasks: "x"` (not a list) -> `next_steps: is required ...`, the same as HEAD. Not a regression, but the message talks about next_steps when `tasks` was malformed (a note; `tasks: must be a list` would be clearer).
- `tasks: None`, no plan field, `next_steps: []` alone -> `next_steps: is required ...`. These are unchanged from HEAD and the criterion does not cover them.
- A validation error together with a check failure -> only the validation error is reported (validation runs first per DESIGN §8); nothing written.
- The new CheckError is raised inside `Checkpoint.from_dict`. Read paths (`bundle.read_bundle`, flat-file load) never pass a `tasks` key, so loading existing checkpoints is unaffected. The eval pipeline (`eval/pipeline.py:203`) will now get a CheckError for a compaction output with `tasks: []`. CheckError subclasses ValidationError, so that path still handles it.

## Regression sweep
Attempt 2 adds one branch to `model._next_steps` and one store test. I ran all 34 cases against HEAD (5366c3a) and the working tree. The differences are exactly the intended ones: checks 1–3 now reject the bad-quote, no-quote, all-done and multiple-failure cases, and the four explicit-empty-`tasks` variants changed from `ValidationError: next_steps: is required` to the check-3 CheckError. Every other case is unchanged: valid saves, old-only saves, decisions, secrets, `tasks: None`, `tasks: "x"`, no plan field, `next_steps: []`.

## For the builder (FAIL only)
1. **`tasks: []` through the MCP tool still gives the old error.**
   - Reproduce: in an MCP session (for example `tests/test_server.py::_run_stdio`), `call_tool("save_checkpoint", {"chat_name":"c","checkpoint_name":"n","objective":"o","current_step":"s","tasks":[]})`.
   - Got: `Error executing tool save_checkpoint: next_steps: is required: give \`tasks\` (preferred) or \`next_steps\``.
   - Cause: `server.py` line ~171 `tasks: List[TaskIn] = Field(default_factory=list, ...)` and line ~196 `if tasks: data["tasks"] = ...`. An explicit `[]` can't be told apart from an absent field, and it is dropped.
   - Correct looks like: the same check-3 CheckError text as the store, with isError True. For example, make the parameter `Optional[List[TaskIn]] = None` and forward it when `tasks is not None`. Check that the list_tools schema and any tests on required/optional fields still pass. Add an MCP test with `tasks: []`.

## Notes (not failure causes; carried from attempt 1)
1. A dropped apostrophe is rejected (`"Let's ship it"` vs quote `"lets ship it"`). This follows DESIGN §8 (punctuation -> space), but small models often drop apostrophes. Deferred by the builder.
2. Different secrets match after redaction (both become `[REDACTED]`). This is inherent to redact-then-compare.
3. A resumed save that repeats a parent user task without user_turns is rejected until F-005 carries user_turns forward. F-005 QA should check it.

Scratch dirs `$HOME/qa-tmp` and `$HOME/qa-old` were removed after the run.
