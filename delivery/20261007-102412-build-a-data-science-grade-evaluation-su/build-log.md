
## F-001 attempt 1
- What changed:
  - src/ai_checkpoint/eval/generate.py (new): seeded, model-free generator; 8-exchange storylines per task type (coding webhook-dedupe service; data-analysis churn study) with seeded parameters and filler exchanges inserted at seeded positions (never splitting a question from its decision, intro first, wrap-up last); writes answer_key, environment manifest with labelled traps, secret_values and a `meta` block (message indexes of planted turns, filler indexes).
  - src/ai_checkpoint/eval/fillers.py (new): 51 coding and 49 data-analysis filler exchanges (varied side questions, no planted facts).
  - src/ai_checkpoint/eval/scenario.py: optional `kind`, `target` on probes; optional `answer_key`, `environment`, `secret_values` on scenarios, validated with field-naming errors (e.g. `probes[0].kind`); old files unchanged.
  - src/ai_checkpoint/eval/cli.py: `generate --seed N (default 7) --out DIR` subcommand (exit 1 if --out is a regular file; argparse exit 2 for a bad seed). `run` unchanged.
  - datasets/handover-v1/: 6 committed scenarios (seed 7) + README.md.
  - tests/test_dataset.py (new): 17 tests covering every F-001 criterion.
- How to run it: `checkpoint-eval generate --seed 7 --out datasets/handover-v1`; `checkpoint-eval run datasets/handover-v1/coding-50.json --model fake --out /tmp/x`
- Tests: `$HOME/aic-venv/bin/python -m pytest -q` -> all pass (199 existing + new dataset tests).
- User-visible changes: new `generate` subcommand in checkpoint-eval; scenario format gains optional fields. Nothing else.
- Notes: `meta` block is an extra top-level key ignored by the loader (for tests/QA). The `target` probe field points into answer_key for F-003 scoring (verbatim[i], decisions[i], correction, next_step, environment.<cat>). Next-step required_terms: coding [migration filename, staging, replay]; data [logistic, slide]. rm is not permitted in the mounted folder, so the dataset was regenerated in place (overwritten).

## F-002 attempt 1
- What changed:
  - src/ai_checkpoint/eval/models.py: `CallTimeout`, `call_with_timeout` (daemon-thread guard), `DEFAULT_TIMEOUT=120`; FakeModel batched answer (`{"questions": [...]}` -> JSON array) and batched judge (`{"items": [...]}` -> JSON array), plus env fault injection `CHECKPOINT_EVAL_FAKE_DELAY` and `CHECKPOINT_EVAL_FAKE_FAIL_FIRST`; OpenAI/Anthropic clients get `timeout=`, OpenAI also `base_url` from `OPENAI_BASE_URL`; `make_model(..., timeout)`.
  - src/ai_checkpoint/eval/pipeline.py: `Caller` (guard + 1 retry on timeout/ModelError + one stderr progress line per call), `extract_json_list` (tolerates fences/prose), batched `answer_probes` / `judge_answers` (`judge_answer` kept as batch of one), new ANSWER/JUDGE prompts, `run_scenario(scenario, model, timeout, progress)` makes 8 calls. Bad replies: wrong count/unparseable -> probes get `error` + null scores; a call failing twice -> variant `failed` (answer/judge) or CheckpointError (compact/summarize).
  - src/ai_checkpoint/eval/cli.py: `--timeout`, `--force` on `run` and new `suite`; overwrite refusal; `suite` one folder per scenario, duplicate-name and existing-results.json checks before any model call, continues after a failed scenario and exits 1.
  - tests/test_eval.py: updated to batched pattern (8 progress lines on stderr, one answer call per variant), stubs accept **kw. tests/test_runner.py (new): 23 tests for F-002 criteria.
- How to run it: `checkpoint-eval run examples/scenarios/invoice-sync.json --out DIR [--timeout 120] [--force]`; `checkpoint-eval suite datasets/handover-v1/*.json --model fake --out DIR`
- Tests: `$HOME/aic-venv/bin/python -m pytest -q` -> 239 passed.
- User-visible changes: stderr now shows one progress line per model call (`[name] answer (checkpoint) [3/8] 0.1s`); `run` refuses to overwrite an existing results.json without `--force`; answer/judge prompts changed (batched JSON arrays), so real-model results are not comparable with earlier per-probe runs; 8 calls per scenario instead of 2 + 6*probes; OpenAI client now uses `OPENAI_BASE_URL` explicitly and the timeout; failed variants now show `2 attempts` errors.
- Notes: when an answer reply has the wrong count, all probes of that variant get the error and the judge call is skipped (so fewer than 8 calls in that case). Timed-out calls leave an abandoned daemon thread. Progress elapsed is time since scenario start. Counter total is fixed at 8 (stays lower if the checkpoint variant fails validation). F-003 metrics not touched.
