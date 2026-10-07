# Intake

## Understanding
Extend the checkpoint format with two things the first real resume showed were missing (docs/DOGFOOD.md, gaps 1 and 2): (1) each decision can record the rejected alternatives and how far each got (discussed, prototyped, built then removed), so a resumed chat can say whether X was ever tried; (2) an optional `workspace` section (ROADMAP item 8) recording files/repos, access, connectors, tools, env var names, skills/agents and references, each marked still relevant or done with, which the resume brief turns into a short "Set up first" checklist and an instruction to ask the user before requesting access. Old checkpoints must keep loading and resuming, secrets stay redacted, and the pinned save_checkpoint description hash is updated on purpose.

Class of risk for the change to existing behaviour: any checkpoint written before the change (fields absent, null or empty) must behave exactly as before, including a byte-identical brief. Edges covered: field missing / null / empty list, partially filled workspace, all items `done_with` (no checklist), invalid enum values, and secrets or `NAME=value` pairs placed inside the new fields.

## Size
medium: two additive schema changes touching model, schema description, brief and tests, no new modules or online work.

## Existing project
Python package `src/ai_checkpoint` (stdlib core; MCP server optional). Relevant: `model.py` (Checkpoint dataclass, `from_dict` is the single validation entry point, errors name the field), `schema.py` (save_checkpoint description and field docs), `brief.py` (`render_brief`), `store.py` (`save` runs `redact_obj` recursively over all fields except `resumed_from`, so new nested strings are redacted automatically), `redact.py`. Tests in `tests/`; `tests/test_eval.py` pins the save description by SHA-256 and length. Run: `$HOME/aic-venv/bin/python -m pytest -q` from the repo root (117 passing).

## Recommended stages
build, qa. Requirements are concrete (ROADMAP item 8 already specifies the content); no research or design stage needed.

## Assumptions
- Field names: `decisions[].rejected` = list of `{option, how_far, note?}` with `how_far` in `discussed | prototyped | built_then_removed`; `workspace` item status in `still_relevant | done_with`. Builder may adjust exact names inside `workspace` but must keep criteria checkable.
- All new fields are optional; default empty; no migration of existing files in ~/.ai-checkpoint (unreachable and unnecessary).
- Env var entries given as `NAME=value` are reduced to `NAME` rather than rejected, so a save never fails over it.
- Resume-time checks that paths/branches/tools still exist (ROADMAP open point) are out of scope; the checklist is advisory only.
- Credential paths (e.g. `~/.ssh/...`) are covered by the save description telling the model not to record them; no new redaction pattern for paths.
- The brief for checkpoints without the new data stays byte-identical; the "Set up first" section appears only when there is at least one still-relevant item.

## Open questions
