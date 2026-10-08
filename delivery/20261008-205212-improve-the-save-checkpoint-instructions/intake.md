# Intake

## Understanding
Tighten the save_checkpoint instructions (SAVE_INSTRUCTIONS and FIELD_DESCRIPTIONS in src/ai_checkpoint/schema.py, which feed both the MCP tool description and the eval compaction prompt) to close three gaps measured in eval-runs/2026-10-09-handover-v2-haiku: (1) the user's own stated plan gets rewritten and later parts dropped; (2) done_with workspace items (abandoned folder paths, old names after rename, unused connectors/tools, env var names) are omitted; (3) rejected alternatives are lost when the reason was short. Class of problem: lossy compaction of user-stated content the instructions treat as optional. Edges: multi-part plans (all parts, order kept), plan absent (no marker, AI steps only), workspace with only done_with items, decisions with no alternatives (rejected stays empty), old checkpoints without these fields (render byte-identically). Real effect is model behaviour, measured later by re-running the v2 Haiku eval; this delivery is checked offline only.

## Size
small: text changes in one module plus deliberate test pin updates and a few phrase-presence tests.

## Existing project
Python package src/ai_checkpoint (schema.py = single source of the instructions; server.py builds the MCP tool from it; brief.py renders the resume brief; eval/pipeline.py uses compaction_system_prompt()). Tests: `$HOME/aic-venv/bin/python -m pytest -q` (307 passed at HEAD 876e689). Pinned description sha/len in tests/test_eval.py (~line 352); golden old-format brief in tests/fixtures/old_format_brief.golden.md checked by tests/test_rejected.py.

## Recommended stages
build, qa. No design/research needed; the change is wording plus test pins.

## Assumptions
- "The brief should make the user's own plan clearly identifiable" is met by a fixed literal prefix `User's plan:` that the saver writes on those next_steps entries, so brief.py, the checkpoint format and the golden brief stay unchanged. If the user wants a separate brief label/section instead, that is a brief layout change and must keep the golden test byte-identical.
- `decisions.rejected` stays structurally optional in the schema/model (old checkpoints have none); only the instruction wording becomes mandatory when alternatives were discussed.
- No eval run or API call in this delivery; the eval-runs/README.md comparison row is added after the user re-runs v2 with Claude Haiku 5.5.

## Open questions
None blocking. (Confirm the `User's plan:` prefix is acceptable vs. a dedicated brief label; build proceeds with the prefix.)
