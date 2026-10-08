# Intake

## Understanding
`checkpoint-eval run` and `suite` currently make every model call sequentially (8 per scenario: compaction, summary, then answer+judge for each of 3 variants). Add `--workers N` (default 8, 1 = today's behaviour, <=0 exits 2) that runs independent calls on a bounded thread pool: scenarios concurrently, and within a scenario compaction || summary || full_history answer, each judge right after its own answer (critical path 3 calls). Output files and stdout must be byte-identical to a sequential run; progress lines must stay whole and correctly counted; per-call timeout/retry and per-scenario failure isolation are preserved.

## Size
small, one feature confined to the eval CLI/pipeline (cli.py _run/_suite/_run_one, pipeline.py Caller/build_handovers/run_scenario), fully checkable offline with FakeModel.

## Existing project
Python package `ai_checkpoint`; eval harness in src/ai_checkpoint/eval/ (cli.py, pipeline.py, models.py with FakeModel honouring CHECKPOINT_EVAL_FAKE_DELAY and CHECKPOINT_EVAL_FAKE_FAIL_FIRST; call_with_timeout already runs each call in a thread). Caller.count is a plain int and _say prints straight to stderr, so neither is thread-safe today. Dataset: datasets/handover-v1 (6 scenarios used by the timing criterion). Tests: `$HOME/aic-venv/bin/python -m pytest -q` (259 pass).

## Recommended stages
build, qa. No design or research needed; the request specifies the concurrency shape.

## Assumptions
- One shared cap across the whole run: a global semaphore (or pool of N) limits in-flight model calls, including retries; call_with_timeout's own helper thread counts as the one call it wraps.
- A timed-out call whose thread is still running in the background counts as finished for the cap (it cannot be cancelled); this is acceptable and matches today's timeout semantics.
- Progress counter k is per scenario and assigned at completion so each scenario still prints 1..total in order of finishing; elapsed time is per scenario since its start. Lines are written under a lock.
- `run` accepts --workers too; for a single scenario it only parallelises calls within that scenario.
- FakeModel's FAIL_FIRST bookkeeping must be thread-safe if shared across threads (test-only fault injection; may be adjusted in models.py).
- Scenario order in stdout and in the error summary follows command-line order; a failed scenario's error line may appear on stderr as soon as it fails.

## Open questions
