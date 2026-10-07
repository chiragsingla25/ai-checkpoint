# Run summary: 20261007-054241-fix-the-checkpoint-format-using-dogfood

## Request
Fix the checkpoint format using the dogfood findings (offline only): record how far rejected alternatives got, and add a `workspace` section (ROADMAP item 8) with a "Set up first" checklist on resume. Old checkpoints must keep working; secrets stay redacted.

## Plan
intake -> build -> qa (nothing skipped). Reason: schema and resume-brief changes with backward-compatibility criteria need independent QA and a regression sweep. Approved by Chirag as proposed.

## Features
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Record how far rejected alternatives got | 1 | PASS (7/7) | ccd473d |
| F-002 Workspace section and 'set up first' checklist on resume | 2 | PASS (9/9) | fb0ec89 |

F-002 attempt 1 failed QA: credentials in URLs (`scheme://user:password@host`) were saved unredacted. Attempt 2 fixed it in `redact.py`; the QA regression sweep found no change for plain URLs, git remotes, emails or other text.

## Rulings
None (no objections).

## User-visible changes
- `save_checkpoint` input schema gains `decisions[].rejected` (`option`, `how_far`: discussed | prototyped | built_then_removed, optional `note`) and an optional `workspace` object; the tool description has two new bullets (pinned hash updated deliberately).
- Resume briefs show `Rejected:` lines under a decision, and a "Set up first" checklist (still-relevant workspace items only, with an instruction to ask the user before requesting access), only when that data exists. Old checkpoints render byte-identically.
- Stored JSON includes `rejected` / `workspace` only when non-empty. Env var values are dropped; only names are kept.
- Passwords in URLs are now saved as `[REDACTED]` in every field.
- `status` is required on every workspace item; a missing one is a validation error and the save is rejected.

## Notes for later
- Required `status` means one omitted status rejects the whole save (the model gets the error and can retry). Consider defaulting to `still_relevant` if this shows up in dogfooding.
- An `export ` prefix stays in env var names; a URL password containing an unencoded `/` or `@` is only redacted up to that character.
- Tests: 173 passed (117 before this run).
