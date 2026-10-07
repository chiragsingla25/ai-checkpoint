
## F-001 attempt 1
- What changed:
  - `src/ai_checkpoint/model.py`: new `Rejected` dataclass, `Decision.rejected`, `HOW_FAR_VALUES`, `_rejected` validator (errors name `decisions[i].rejected[j].option|how_far|note`, `decisions[i].rejected`); `to_dict` writes `rejected` only when non-empty (keeps old shape and the existing store test).
  - `src/ai_checkpoint/brief.py`: decisions render `  Rejected: <option> (<discussed|prototyped|built, then removed>) - <note>` under their decision; decisions without rejected render exactly as before.
  - `src/ai_checkpoint/schema.py`: field descriptions for `decisions`, `decisions.rejected(.option/.how_far/.note)`, and the compaction field type text. `SAVE_INSTRUCTIONS`/`SAVE_DESCRIPTION` deliberately untouched so the pinned hash stays valid (F-002 owns that change).
  - `src/ai_checkpoint/server.py`: `RejectedIn` model (how_far as Literal enum) and `DecisionIn.rejected`.
  - `tests/test_rejected.py` (new, 21 tests), `tests/fixtures/old_format_cp.json` and `tests/fixtures/old_format_brief.golden.md` (golden rendered from the code before any edit).
- How to run it: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q`
- Tests: full suite 138 passed (117 existing + 21 new), 0 failed.
- User-visible changes: save_checkpoint tool input schema gains `decisions[].rejected` and the `decisions` field description is longer (the tool description text itself is unchanged); the compaction prompt for the eval kit lists the new field; briefs show `Rejected:` lines only when rejected items exist; stored JSON includes `rejected` only when non-empty.
- Notes: old-format fixture is read from a hand-placed `cp-003.json` (store resolves path by file name, so the fixture's id and filename match). Golden brief is exercised via Store.get, MCP resume_checkpoint (in-process) and CLI. Multi-line option/note text is collapsed to single-spaced in the brief. Workspace section not touched (F-002).
