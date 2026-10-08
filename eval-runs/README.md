# Eval runs log

Every real evaluation run of the handover eval, kept so results can be compared over time.
Raw outputs (results.json, results.md, handover_*.md per scenario) are copied here from the gitignored `results/` folder.
Add a row and a folder for every new run. Numbers are averages over the run's scenarios; contradictions are totals.

## How to add a run
1. Run: `.venv/bin/checkpoint-eval suite datasets/<dataset>/*.json --model openai --model-name <id> --workers 8 --timeout 90 --out results/<run-name>/`
2. Copy: `mkdir -p eval-runs/<YYYY-MM-DD>-<dataset>-<model> && cp -r results/<run-name>/* eval-runs/<YYYY-MM-DD>-<dataset>-<model>/`
3. Add a row below with the eval-kit commit (`git log -1 --format=%h`) and a one-line note.

## Runs

| Run folder | Date | Model | Dataset | Eval kit commit | Product commit | Notes |
|---|---|---|---|---|---|---|
| 2026-10-07-delivery-restructure-gemini | 2026-10-07 | google/gemini-3.8-flash-20260902 | examples/scenarios/delivery-restructure (1 scenario, 7 probes) | original eval kit (pre 7c02e5b) | pre format fixes | First real signal. Per-probe calls. invoice-sync result was overwritten (lost). |
| 2026-10-08-handover-v1-haiku | 2026-10-08 | anthropic/claude-haiku-5.5 | handover-v1 (6 scenarios, 66 probes) | 9ea622b | 01a75ae+ | Measurement bugs: stale scorer, workspace path matching, strict next-step, impossible facts in v1, coding-50 checkpoint batch lost (12 answers for 11). Do not quote stale/next-step/capture numbers from this run. |
| 2026-10-08-handover-v1-haiku-rescored | 2026-10-08 | (rescore, no calls) | handover-v1 | 4bc1f4b | — | Code-scored metrics recomputed with fixed scorers (see rescored.json). Workspace scored from the brief's 'Set up first' list, so done-with recall is not meaningful. |
| 2026-10-09-handover-v2-haiku | 2026-10-08 (UTC) | anthropic/claude-haiku-5.5 | handover-v2 (6 scenarios, 66 probes) | 251a38e | 01a75ae+ | First clean run. Baseline for product fixes. 2 judge replies malformed (2 probes unscored). |

## Headline comparison

### Handover quality (checkpoint / summary / full history)

| Run | Key-fact recall | Contradictions | Verbatim exact | Stale use | Next step | Brief tokens |
|---|---|---|---|---|---|---|
| 2026-10-07 gemini (1 scenario) | 100% / 95% / 97% | 0 / 0 / 0 | — | — | — | 2148 / 1080 / 2697 |
| 2026-10-08 v1 haiku (raw) | 86% / 79% / 94% | 2 / 5 / 1 | 100% / 89% / 100% | invalid | invalid | 2970 / 1102 / 3116 |
| 2026-10-08 v1 haiku (rescored) | unchanged | unchanged | 100% / 89% / 100% | 0% / 0% / 0% | 80% / 33% / 100% | — |
| **2026-10-09 v2 haiku** | **88% / 78% / 98%** | **2 / 5 / 0** | **100% / 89% / 100%** | **0% / 0% / 0%** | **50% / 33% / 100%** | **3050 / 1027 / 3159** |

### Workspace capture (checkpoint only)

| Run | Recall (all) | Recall still-relevant | Recall done-with | Precision | Status accuracy | Secret leakage |
|---|---|---|---|---|---|---|
| 2026-10-08 v1 haiku (raw) | 39-61% (matcher bug) | — | — | 47-79% | 91-100% | 0 |
| 2026-10-08 v1 haiku (rescored, from brief) | 62% | 85% | ~3% (brief lists still-relevant only) | 70% | 99% | 0 |
| **2026-10-09 v2 haiku** | **82%** | **92%** | **57%** | **75%** | **97%** | **0** |

## Findings log

- **2026-10-09 v2 haiku:** checkpoint beats summary on recall (+10 pts, 5 of 6 scenarios), contradictions and exact code; full history still best on these short chats (<=5k tokens). Product gaps: (1) the user's multi-part next step is rewritten into an implementation plan and later parts drop (3 of 6 misses); (2) done-with items dropped ~40% (abandoned folder path, SNOWFLAKE_PASSWORD name); (3) rejected option lost once (Redis, coding-50). Next: fix save instructions, re-run v2 and compare against this row.
- Limits for all runs: one run per configuration, same model writes/answers/judges, templated chats, 66 probes per handover (differences under ~5 pts are noise).
