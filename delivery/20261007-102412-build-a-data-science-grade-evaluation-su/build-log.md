
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
