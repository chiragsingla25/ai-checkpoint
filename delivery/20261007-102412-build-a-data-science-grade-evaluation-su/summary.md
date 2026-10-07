# Run summary: 20261007-102412-build-a-data-science-grade-evaluation-su

## Request
A data-science grade eval suite and dataset for AI Checkpoint handovers. At the approval gate Chirag cut it to the LEAN version (see request.md "Scope change" and decisions.md): product code unchanged, eval kit only, ~8 model calls per scenario.

## Plan
intake -> build -> qa. Reason: eval-kit features with offline-checkable criteria; independent QA catches regressions in the existing run command.

## Features
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Seeded scenario generator + datasets/handover-v1 (coding, data_analysis x 20/50/100) | 1 | PASS 12/12 | 7c02e5b |
| F-002 Runner fixes (timeout + 1 retry, suite folders, no overwrite) + batched probes | 1 | PASS 11/11 | 0acb460 |
| F-003 Code-scored metrics + workspace capture scoring | 2 | PASS 11/11 | d82d329 |

F-003 attempt 1 failed: secret leakage double-counted, a product-code test tripped on the run folder, and (QA note, fixed too) verbatim matching ignored number boundaries (868 matched 8680).

## Rulings
- Scope ruling at the gate (Chirag): lean version only.
- F-003 criterion 8 (orchestrator, reported to Chirag): secret_leakage = number of distinct secrets found, labelled as measured before save-time redaction.

## User-visible changes
- New commands: `checkpoint-eval generate` and `checkpoint-eval suite`; `run` gains `--timeout` and `--force` and refuses to overwrite an existing results.json.
- Probes are batched: one answer call and one judge call per variant (8 calls per scenario). Progress lines go to stderr.
- results.md gains verbatim exact match, stale-fact use and next-step accuracy columns, and a workspace capture table.
- Product code (save/resume/MCP server/schema) untouched. Tests: 259 passing.

## Known limits (for the write-up)
- Dataset is templated: story steps come in a fixed order, the next step always sits in the final recap, corrections are always flagged ("One correction..."), some decisions are guessable from common practice.
- Stale scorer counts a correct answer that mentions the history ("was 24h, now 48h") as stale.
- Batched probes let one answer influence another slightly; same for every variant.
- FakeModel numbers are meaningless; real numbers need a run with a real model.
