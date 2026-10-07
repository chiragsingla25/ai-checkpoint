VERDICT: PASS

F-001 "Record how far rejected alternatives got", attempt 1. QA verified this independently against the uncommitted working tree. HEAD 21c0624 is the baseline.

Test suite: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q` gave `138 passed in 38.21s`. The suite at HEAD, run from a worktree with PYTHONPATH pointing at the old code, gave `117 passed`. So the 117 existing tests still pass and 21 are new (`tests/test_rejected.py`: `21 passed`).

| Criterion | Result | Evidence |
|---|---|---|
| 1. Optional `rejected` list `{option, how_far in discussed/prototyped/built_then_removed, note?}`; `from_dict` accepts it, `to_dict` round-trips it unchanged (pytest) | met | `test_rejected_roundtrips_unchanged` passes: GOOD list of 3 items, one with a note, comes back `==` from `to_dict`, and a second `from_dict(to_dict())` gives the same output. Manual check: all three how_far values accepted; output matches input. |
| 2. No `rejected` key, `null`, or `[]` loads and round-trips with an empty list (pytest) | met | `test_rejected_absent_null_empty_gives_empty_list[absent/None/[]]` passes. `cp.decisions[0].rejected == []` and it stays empty after a round-trip (the key is not written when empty). |
| 3. ValidationError names the exact field: bad how_far -> `decisions[0].rejected[0].how_far`; empty/missing option -> `...rejected[0].option`; non-list -> `decisions[0].rejected` (pytest) | met | `test_rejected_validation_names_field` covers 9 cases and passes. Manual run gave: `"tried"` -> `decisions[0].rejected[0].how_far`; `"Prototyped"` (wrong case), `["prototyped"]` and `null` how_far -> the same field; `option: null` and `option: 5` -> `decisions[0].rejected[0].option`; `rejected` set to `0`, `False`, `""` or `{}` -> `decisions[0].rejected`; a bad 2nd item -> `decisions[0].rejected[1].how_far`; a bad item on the 2nd decision -> `decisions[1].rejected[0].how_far`. |
| 4. `render_brief` lists each rejected alternative under its decision in readable words (`Rejected: hooks (prototyped)`, `built, then removed`), plus the note when present (pytest asserts strings) | met | `test_brief_lists_rejected_in_words` passes and also checks the order: decision, then Rejected, then Completed. A manual CLI `resume` of a saved checkpoint printed `  Rejected: hooks with Bearer [REDACTED] (prototyped) - password=[REDACTED]` and `  Rejected: daemon (built, then removed) - token=[REDACTED]` under `- Use MCP / Reason: r`. |
| 5. save_checkpoint schema/description in schema.py documents `rejected` and the allowed how_far values (`get` of the registered tool's input schema) | met | `create_server().list_tools()` -> save_checkpoint `inputSchema.$defs.RejectedIn`: `required ["option","how_far"]`, how_far `enum ["discussed","prototyped","built_then_removed"]` with a description naming all three; `DecisionIn.properties.rejected.description` explains how_far and note. `test_save_schema_documents_rejected` passes. |
| 6. Secrets in `option`/`note` (`sk-ant-...`, `token=abcd1234efgh`) stored redacted by `Store.save` (pytest) | met | `test_save_redacts_secrets_in_option_and_note` passes and reads the raw file. Manual save through the MCP `save_checkpoint` and a CLI `save --file` into an isolated AI_CHECKPOINT_HOME produced a file on disk containing `"option": "hooks with Bearer [REDACTED]"`, `"note": "password=[REDACTED]"`, `"note": "token=[REDACTED]"` and `"option": "cron [REDACTED]"` (the input was `sk-ant-api03-ZZZ...`). A grep for the raw secrets returned 0 matches. |
| 7. Old-format fixture shaped like cp-001..cp-003 loads via `Store.get`, resumes via MCP `resume_checkpoint` and the CLI, and the brief is byte-identical to a golden file from pre-change code (pytest) | met | `test_old_fixture_*` (4 tests) pass. The golden file was checked independently: QA rendered `tests/fixtures/old_format_cp.json` with the HEAD code (worktree; `__file__` = `qa-wt/src/ai_checkpoint/__init__.py`) and with the new code, and compared both against the golden file with `cmp`. Results: `OLD==GOLDEN` and `NEW==GOLDEN`. The fixture's decisions have only `decision` and `reason` and there is no `workspace`. |

## Extra checks
- MCP `save_checkpoint` with `how_far: "tried"` is rejected by the pydantic Literal (`decisions.0.rejected.0.how_far Input should be 'discussed', 'prototyped' or 'built_then_removed'`). An empty `option` is rejected with `decisions[0].rejected[0].option: must not be empty`.
- CLI `save --file` with `how_far: "tried"` returns exit 1 and the message `error: decisions[0].rejected[0].how_far: must be one of discussed, prototyped, built_then_removed, got 'tried'`.
- Multi-line option text is collapsed to single spaces in the brief (`multi line opt`). A whitespace-only note is not rendered.
- Notes, not failures:
  - `note: null` or `note: ""` is accepted, and the `note` key is dropped on `to_dict`. That is fine, but such input does not come back key-for-key.
  - A whitespace-only note (`"   "`) is stored as-is but hidden in the brief.
  - Unknown extra keys inside a rejected item are silently dropped. This matches how decisions already handle extra keys.
- The real store at ~/.ai-checkpoint was not touched. The cp-001..cp-003 coverage relies on the fixture.

## Regression sweep
Code paths touched: `model.Decision` (new field), `Checkpoint.to_dict` (decisions now go through `_decision_dict`), `model._decisions` (calls the new `_rejected` validator), `brief.render_brief` decisions section (new `_decision`), `schema.FIELD_DESCRIPTIONS["decisions"]` plus new keys, `schema.COMPACTION_FIELDS` decisions type, and `server.DecisionIn`/`RejectedIn`.

QA ran the same script under the old code (worktree at HEAD, PYTHONPATH confirmed by `__file__`) and the new code, comparing the hash of `to_dict` JSON plus `render_brief` output, or the ValidationError field and message. Inputs: the fixture; empty, missing and null decisions; multi-line and unicode/tab decision text; a decision whose text starts with "Rejected:"; an extra key on a decision; empty decision text; missing reason; a string for decisions; a string decision item; `rejected: null`; `rejected: "junk"`.
- All outputs and errors are identical except one: `rejected: "junk"` was silently ignored before and is now `ValidationError decisions[0].rejected`. Criterion 3 requires this.
- `SAVE_DESCRIPTION`, `SAVE_INSTRUCTIONS` and `SAVE_TOOL_SUFFIX` hashes are identical old vs new, so the pinned eval hash tests are unaffected.
- Tool listing diff (all tools, old vs new): the only changes are the added `DecisionIn.rejected`, the new `RejectedIn` def, and the longer `decisions` field description. The other tools are unchanged.
- The full old suite (117 tests) still passes under the new code, as part of the 138.

No unrequired behaviour changes were found. The worktree was removed and the scratch files and store were deleted.
