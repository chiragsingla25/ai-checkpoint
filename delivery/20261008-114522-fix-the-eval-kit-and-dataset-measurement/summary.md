# Run summary: 20261008-114522-fix-the-eval-kit-and-dataset-measurement

## Request
Fix the measurement bugs found in the first real eval run (results/handover-v1-haiku, Claude Haiku 5.5). Eval kit and dataset only; product code unchanged.

## Plan
intake -> build -> qa. Reason: scorer and dataset changes decide what the published numbers say; each needs independent QA against the real run's answers.

## Features
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Fixed code scorers (stale, workspace capture, next step) + `rescore` command | 2 | PASS 13/13 | 4bc1f4b |
| F-002 One corrective retry for batched replies with the wrong item count | 1 | PASS 4/4 | 03746be |
| F-003 Dataset generator fix, self-check, datasets/handover-v2 | 1 | PASS 7/7 | 8e1b5e4 |

F-001 attempt 1 failed: the new stale scorer under-flagged answers that present the old value as current. Attempt 2 decides which value is asserted as current. Known limit (QA note): when both values appear with no history/negation wording, the scorer follows the last-mentioned value; 6 hand-made adversarial cases still score wrong. None of the 17 real answers are affected.

## Rescore of the first Haiku run (no model calls)
`checkpoint-eval rescore` on a copy (results/handover-v1-haiku-rescored):
- Stale-fact use: 0% for all three handovers (was wrongly 67-100%).
- Next step: checkpoint 80% (was 60%), summary 33%, full history 100%.
- Verbatim: checkpoint 100%, summary 89%, full history 100% (unchanged).
- Workspace (scored from the brief's 'Set up first' section, since rescore has no checkpoint JSON): still-relevant recall 85% avg, precision 70%, status accuracy 99%, leakage 0. Done-with recall ~3% because the brief only lists still-relevant items by design; the v2 live run scores the checkpoint JSON instead.
- Judge recall is unchanged by rescore and still includes the impossible facts fixed in handover-v2.

## User-visible changes
- New `checkpoint-eval rescore <dir> [--dataset ...] [--strict-next-step]` writes rescored.json beside results.json.
- New `generate --version handover-v2`; datasets/handover-v2 added; handover-v1 unchanged (default still v1).
- Batched answer/judge replies with a wrong item count get one corrective retry (one extra call).
- Workspace capture adds recall_still_relevant and recall_done_with. Tests: 307 passing. Product code untouched.
