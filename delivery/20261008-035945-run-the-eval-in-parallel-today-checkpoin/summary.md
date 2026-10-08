# Run summary: 20261008-035945-run-the-eval-in-parallel-today-checkpoin

## Request
Run the eval in parallel: `--workers N` (default 8) for `checkpoint-eval run` and `suite`, with byte-identical results to a sequential run.

## Plan
intake -> build -> qa. Reason: concurrency changes are easy to get subtly wrong; independent QA checks identical outputs and the in-flight cap.

## Feature
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Parallel eval with --workers N for checkpoint-eval run and suite | 1 | PASS 13/13 | 064e5ec |

## User-visible changes
- New `--workers N` on run and suite (default 8; 1 = old sequential order; 0/negative exits 2).
- Scenarios run concurrently; inside a scenario only compaction -> answer -> judge are sequential. Fake 6-scenario run with 0.5s delay: ~24s sequential vs ~3s at 8 workers.
- Progress lines arrive in completion order when parallel (use --workers 1 for the fixed order). Output files and stdout tables are identical to sequential.
- tests/test_runner.py progress-order test now pins --workers 1. Tests: 282 passing. Product code unchanged.
