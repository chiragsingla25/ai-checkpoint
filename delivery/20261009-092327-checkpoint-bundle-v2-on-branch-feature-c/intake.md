# Intake

## Understanding
Replace the single-file checkpoint (`checkpoints/cp-NNN.json`) with a per-chat folder bundle (manifest, plan, decisions, facts, workspace, user turns, verbatim files, open questions, rendered brief, per-chat events log), still inside the one stdlib MCP server with one git commit per save. On top of it: a structured plan with server-computed next action, a brief that opens with 'Next action' and lists 'No longer needed' items, save-time checks returned as fixable errors, carry-forward of plan updates by task id from resumed chats, and eval support so handover-v2 can measure it. Goal is next-step accuracy 50% -> >=90% without key-fact recall dropping below 88%; the branch is pushed only if a real eval run shows that.

## Size
large: new storage layout plus migration-free compatibility, a new save schema, checks, carry-forward, and eval changes across store/model/schema/server/brief/eval (~4k lines today, 308 tests).

## Existing project
Python package `src/ai_checkpoint` (schema.py = single source of save instructions/field descriptions; model.py = Checkpoint dataclass + validation; store.py = GitStore, flat `checkpoints/cp-NNN.json`, global ids, renumbering, lock, git commit; brief.py = render_brief; server.py = MCP tools save/list/get/resume; redact.py). Eval kit in `src/ai_checkpoint/eval/` (pipeline `_compaction_handover` validates JSON with Checkpoint.from_dict and renders the brief without the store; FakeModel in models.py). Golden fixtures exist: tests/fixtures/old_format_cp.json and old_format_brief.golden.md. Datasets handover-v1/v2 (6 scenarios). Baseline in eval-runs/2026-10-09-handover-v2-haiku. Tests: `$HOME/aic-venv/bin/python -m pytest -q` (308 pass). On branch feature/checkpoint-bundle-v2, clean apart from this run folder.

## Recommended stages
build, qa. Build in feature order F-001..F-006; each ships and tests on its own (F-003..F-005 depend on F-002; F-006 on F-003/F-004). QA should run the full test suite after each and the offline fake suite on handover-v2 after F-006.

## Assumptions
- All new saves write bundles; old flat files are read in place, never migrated or rewritten.
- Chat folder name is a safe slug of chat_name with case-insensitive grouping matching today's renumbering; exact rule fixed in DESIGN-v2.md.
- Task ids are per-checkpoint plan ids (t-N), stable across carry-forward; checkpoint ids stay global cp-NNN.
- brief.md is written for convenience but resume always re-renders from the data files.
- The >=90% / >=88% target is checked by a manual real-model run (needs an API key), not by offline acceptance criteria; "push only if evals improve" is a release gate, not part of build.
- No new dependencies (stdlib plus the existing MCP/pydantic used by server.py).

## Open questions
1. In the eval, when save checks reject the compaction output, should the pipeline feed the errors back to the model for one retry (mirroring the in-chat "fix in the same turn" flow) or score it as a failed save? This changes pipeline code and the measured numbers.
2. Quote check strictness: exact substring only, or whitespace/case-normalised? Exact is what the request says but may reject many real saves.
3. Should `get_checkpoint` on a bundle return the new structured shape, the old flat shape, or both? Affects API consumers and tests.
4. If a chat is resumed under a different chat_name, which chat folder does the new bundle go in (the new name or the parent's)?
