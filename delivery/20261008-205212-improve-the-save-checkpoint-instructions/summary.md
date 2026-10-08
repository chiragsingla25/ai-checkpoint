# Run summary: 20261008-205212-improve-the-save-checkpoint-instructions

## Request
Fix three save-instruction gaps measured in eval-runs/2026-10-09-handover-v2-haiku: the user's own next-step plan gets rewritten, done-with workspace items get dropped, rejected options sometimes missing.

## Plan
intake -> build -> qa. Reason: product instruction change; QA confirms old checkpoints and the tool contract are untouched.

## Feature
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Save instructions keep the user's plan, done-with items and rejected options | 1 | PASS 13/13 after ruling on the 'full suite passes' objection | d8b99c7 |

## Rulings
- QA objection on "full suite passes": the eval-era guard test fails while product code is uncommitted. Ruling: suite must be green after commit. After commit: 308 passed (two runs); one earlier run right after commit showed 1 failure that did not reproduce (likely the timing-sensitive parallel test; noted as flaky).

## User-visible changes
- save_checkpoint description +550 bytes: next_steps start with the user's own plan, each step prefixed `User's plan:`; workspace also lists done-with items (full paths, old names, unused connectors/tools, env var names) marked done_with; every decision with discussed alternatives fills `rejected`.
- Format, store, MCP tools and brief layout unchanged; old checkpoints render byte-identically.

## Open (design note from QA)
done_with items are stored in the checkpoint JSON but never shown in the resume brief, so a resumed chat still cannot answer "which folder did we stop using?". Showing a short "No longer needed" line in the brief would be a separate, small brief-layout change (needs Chirag's OK).
