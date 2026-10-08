
## F-001 attempt 1
- What changed: src/ai_checkpoint/schema.py (3 SAVE_INSTRUCTIONS bullets amended; FIELD_DESCRIPTIONS next_steps, workspace, decisions.rejected updated); tests/test_eval.py (pinned sha/len updated with comment, paragraph-break assertion updated, new test_save_instructions_carry_the_three_rules).
- How to run it: $HOME/aic-venv/bin/python -m pytest -q
- Tests: 307 pass, 1 expected failure while uncommitted: tests/test_metrics.py::test_product_code_unchanged fails because it requires `git status src/ai_checkpoint` to be clean outside eval/ (a tree-state guard; passes once the orchestrator commits). Total with new test: 308.
- User-visible changes: save_checkpoint tool description grew 2279 -> 2829 bytes (sha 3d9a427f...); compaction prompt and tool field descriptions changed accordingly. Saved briefs may now show "User's plan:" prefixed next steps. No format/brief/store change.
- Notes: exact new text:
  * rejected bullet: `- For EVERY decision where alternatives were discussed, list each one in `rejected` with how far it got (discussed, prototyped, built_then_removed), even when the reason is short or the option was only mentioned. Leave `rejected` empty only if no alternative came up.`
  * workspace bullet (added after "`done_with` if not."): `List `done_with` items too; do not leave them out. Examples: an abandoned folder (give its full path), an old file name after a rename, a connector or tool no longer used, an env var NAME that was used.`
  * next_steps bullet (added): `If the user stated their own plan for what comes next, `next_steps` must START with that plan: the user's own words, every part, in order, each step beginning with the exact text "User's plan:". Then add your own steps. If the user gave no plan, do not write "User's plan:".`
  * FIELD_DESCRIPTIONS next_steps: `Ordered, concrete instructions for continuing from the current step. At least one. If the user stated their own plan, it comes first, in their words and in order, each step starting with "User's plan:"; your own steps come after.`
  * FIELD_DESCRIPTIONS workspace: appended `, but done-with items must be listed too, not dropped.` after the 'Set up first' clause.
  * FIELD_DESCRIPTIONS decisions.rejected now starts: `` `rejected` must hold every alternative discussed for this decision, even when the reason is short; empty only if none came up. Each as {option, how_far, note?}... `` (rest unchanged).
