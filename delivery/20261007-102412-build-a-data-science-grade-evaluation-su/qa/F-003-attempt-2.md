VERDICT: PASS

F-003 attempt 2. 11 of 11 criteria met. Criterion 8 is checked against the ruling in decisions.md: secret_leakage counts DISTINCT secrets found in the checkpoint JSON or the brief, labelled as measured before save-time redaction. `ai_checkpoint.eval.metrics.__file__` resolves to the working tree. `$HOME/aic-venv/bin/python -m pytest -q` gives **259 passed**.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Three code metrics in each aggregate, still 8 calls per scenario, results.md columns | met | `checkpoint-eval suite datasets/handover-v1/*.json --model fake --out ~/qa-tmp/s` gives rc=0, 48 stderr progress lines and 6 results.json files. Every variant has `verbatim_exact_match`, `stale_fact_use`, `next_step_accuracy`. The results.md header has columns `verbatim exact`, `stale-fact use` and `next-step acc`. |
| 2 | Verbatim exact substring; criterion examples | met | `("run pytest -q -k sync","pytest -q -k sync")=1`, `("pytest -k sync -q",…)=0`. `0.873`/`0.8732` scores 0 in **both** directions now. Surrounding whitespace is ignored (=1); a case change scores 0. Extra cases: `8680`/`1868`/`1,868` vs `868` = 0; `868.`, `868,`, `(868)` = 1; a backticked command = 1; `VALUES (%s)` vs `VALUES (%` = 1; empty strings = 0. |
| 3 | Stale: old = 1, only new = 0, `50` in `500` not counted | met | 1 / 0 / 0, and `limit 50` = 1. |
| 4 | Next-step accuracy: all required terms | met | All terms present = 1; a missing term = 0. The builder's test checks a 2-probe average of 0.5. |
| 5 | Old scenarios: the three metrics null / `n/a` | met | Both `examples/scenarios/*.json`: all None. Row reads `\| checkpoint \| ok \| 24% \| 0 \| n/a \| n/a \| n/a \| 2224 \|`. No `workspace_capture` block. |
| 6 | `workspace_capture` present iff manifest; runs without one | met | Present in all 6 dataset results (e.g. coding-20: 0.7778 / 0.9333 / 0.5 / 0). Absent for the old examples, which run with rc 0. |
| 7 | Category + normalised key; 4/3/2/1 example gives 0.50 / 0.67 / 0.50 | met | My own mixed-category example uses `./b` vs `b/` and `${HOME}/w` vs `~/w/`. It gives 0.5 / 0.6667 / 0.5. |
| 8 | (per ruling) distinct leaked secrets in checkpoint JSON or brief; hand-built env_vars leak = 1; LEAK flagged; FakeModel dataset 0; labelled before save-time redaction | met | Through `run_scenario`: secret as an env_vars name gives **1** and `LEAK (1)`. The same secret twice in notes gives 1. Two different secrets give 2 and `LEAK (2)`. Unit cases: one secret repeated 3 times = 1; a duplicate in `secret_values` = 1; an empty secret string is ignored. Dataset with FakeModel: 0 on all 6. results.md caption: "secret leakage is measured on the model's checkpoint before the product's save-time redaction", and the column header reads "secret leakage (distinct secrets, before save-time redaction)". |
| 9 | FakeModel workspace heuristic, no env values, recall > 0, validates | met | All 6 raw compactions pass `Checkpoint.from_dict`. No secret value appears in the raw output. env_var names only (e.g. `CARRIER_WEBHOOK_SECRET`, `SNOWFLAKE_PASSWORD`). capture_recall is 0.67–0.78. |
| 10 | Empty/missing workspace: recall 0, precision null, leakage 0 | met | Workspace None, `{}` or `{"files":[]}` gives 0.0 / None / 0 with no error. |
| 11 | Offline suite e2e + product code unchanged | met | Suite as in row 1. `git status --porcelain -- src`: only `src/ai_checkpoint/eval/{models,pipeline,report}.py` modified and `eval/metrics.py` new. No change to save/resume, server, schema, brief, model or redact. |

## Extra checks
- An env_vars entry `X_KEY=SECRETVAL` scores 0. The product schema strips the value in `Checkpoint.from_dict` before scoring, which is consistent with "before save-time redaction" (the schema normalisation is not redaction).
- The rewritten `test_product_code_unchanged` now passes with the uncommitted run folder present. It checks `git status -- src/ai_checkpoint` outside `eval/`.
- Dataset verbatim aggregates are unchanged from attempt 1 (FakeModel answers never had verbatim values inside longer tokens).

## Regression sweep
Touched since HEAD: `FakeModel._compact` (+ `_redact`, `_workspace`), `_compaction_handover`, `build_handovers`, `_probe_entry`, `_aggregate`, `run_scenario` (+ `_workspace_capture`), `markdown_table`, and the new `metrics.py`. HEAD was checked out in worktree `~/qa-wt7` (`pipeline.__file__` confirmed there). Both versions ran FakeModel on the 2 example scenarios and the 6 dataset scenarios:
- key_fact_recall, contradictions, probes_scored and status are identical everywhere. Summary and full_history handovers and answers are identical.
- The checkpoint brief_tokens grew (e.g. coding-20 1100 -> 1181, invoice-sync 2160 -> 2224) because the brief now renders the workspace that criterion 9 requires. Dataset checkpoint answers differ only by those workspace lines.
- `run`: rc 0, then rc 1 on re-run (overwrite refusal), in both versions. `generate --seed 7`: output is identical in old and new and matches the committed `datasets/handover-v1` (apart from its README).
No unrequired change found. Worktree removed and pruned; `~/qa-tmp` deleted.

## Notes (not verdict factors)
- Stale scorer: an answer that states both old and new values ("was 24 hours, now 48 hours") scores stale = 1, so it can't be gamed that way. The cost is a false positive when a correct answer mentions the history.
- Verbatim scorer: the token-boundary fix removes the `868`-inside-`8680` problem. A very long answer that pastes the handover can still score 1. The boundary is stricter than plain "exact substring", but every example in the criterion holds.
- Underscore is not treated as a token character, so `868_x` still matches `868`. This is minor.
