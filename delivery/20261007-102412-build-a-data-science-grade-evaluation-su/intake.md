# Intake

## Understanding
Lean eval kit only (scope change at the approval gate, see decisions.md): a seeded, model-free scenario generator plus a committed 6-scenario dataset (coding and data_analysis x 20/50/100 messages) with answer keys and environment manifests including traps; minimal runner fixes (per-call timeout with one retry, `suite` with one folder per scenario, no overwrite without `--force`); batched probes so each scenario costs about 8 model calls; and code-scored metrics (verbatim exact match, stale-fact use, next-step accuracy, brief tokens) plus workspace capture scoring. The product (save/resume/MCP server) does not change. Runner fixes address docs/DOGFOOD.md: a Qwen run hung for ~1 hour, and invoice-sync results were overwritten through a shared `--out`.

## Size
large: three features across the runner, the scenario format, FakeModel, scoring and a committed generated dataset, though each feature on its own is medium.

## Existing project
Python >= 3.10 package `ai-checkpoint`, src layout, no core dependencies; extras mcp/anthropic/openai/dev. Eval code in src/ai_checkpoint/eval/ (cli.py with one `run` subcommand; models.py with the deterministic FakeModel dispatching on `TASK:` system prefixes plus lazy OpenAI/Anthropic adapters; pipeline.py currently making one answer call and one judge call per probe; report.py; scenario.py). The checkpoint model (model.py) already has a `workspace` section with 8 categories and status still_relevant|done_with; FakeModel's compaction leaves it empty today. Two example scenarios in examples/scenarios/. Tests: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q` -> 199 passed at intake. tests/test_eval.py imports `judge_answer` and checks per-probe answer-call isolation; batching will require updating those tests. The venv has no openai, numpy or matplotlib (none needed now).

## Recommended stages
build, qa. Build order F-001 (dataset, which F-003 needs for answer keys and manifests), F-002 (runner and batching), F-003 (metrics and capture). QA after each feature.

## Assumptions
- `run SCENARIO --out DIR` keeps writing directly into DIR (existing tests depend on it). The new `suite` subcommand writes OUT/<scenario-name>/.
- Timeout applies per call and the single retry also covers ModelError from the API; a call that fails twice ends that variant's step as a recorded error (or a clean exit 1 for compaction/summary API failures, matching the current behaviour).
- Offline fault injection uses FakeModel env vars (CHECKPOINT_EVAL_FAKE_DELAY, CHECKPOINT_EVAL_FAKE_FAIL_FIRST); build may rename them if documented.
- Batched answer and judge replies are JSON lists in probe order; results.json keeps one entry per probe so existing readers still work.
- The scenario format gains optional fields (probe `kind`, `answer_key`, `environment`, `secret_values`); old files stay valid.
- Fake secrets are obviously fake (`sk-fake-...`), so committing them is safe.
- Dataset lives in `datasets/handover-v1/`; the hand-written examples stay in examples/scenarios/.
- Brief tokens keeps using the existing `estimate_tokens`.
- Out of scope (per owner): last-20 and no-handover variants, repeats and bootstrap CIs, parallel workers, resume-from-cache, the restore stage with mock tools, the report command and charts, and any drift test.

## Open questions
None.
