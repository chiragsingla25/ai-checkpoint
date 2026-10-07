VERDICT: PASS

QA for F-001 attempt 1. All checks run on the uncommitted working tree (editable install, `$HOME/aic-venv`). Scratch output was written under `$HOME/qa-tmp`. Checks were done with my own script (`check.py`), which works out indexes from message text. It does not trust the generator's `meta` block.

| Criterion | Result | Evidence |
|---|---|---|
| 1. `generate --seed 7 --out DIR` writes exactly 6 files named `{coding,data_analysis}-{20,50,100}.json`; no model, network or key | met | `env -u OPENAI_API_KEY ... checkpoint-eval generate --seed 7 --out ~/qa-tmp/ds` gave rc=0 and printed and wrote exactly those 6 files. `generate.py` imports only json, random, pathlib, typing and `.fillers`, so nothing touches the network or a model. |
| 2. Determinism: seed 7 twice gives byte-identical files; seed 8 changes the message text of every file | met | `diff -r ds ds2` showed no difference. The seed-7 output is also byte-identical to the 6 committed files. Seed 8 vs seed 7: the `messages` list differs in all 6 files, with only 3 to 8 identical messages per file (for example coding-50 has 5/50 identical, data_analysis-100 has 4/100). |
| 3. Lengths are within ±10% and every role is user or assistant | met | Counts are exactly 20/50/100 for seeds 7, 8, 0, -3, 1-5 and 999999999999. No other roles appear (`check.py`). |
| 4. Every generated file loads with `load_scenario` and runs with `run --model fake` (exit 0); the 2 example scenarios still load and run unchanged | met | All 6 files gave rc=0, each writing results.json, results.md and 3 handover_*.md files. `examples/scenarios/{delivery-restructure,invoice-sync}.json` give rc=0, and their results directories and stdout are byte-identical between HEAD and the working tree (see the regression sweep). |
| 5. answer_key: at least 2 decisions with reason and rejected alternative; a verbatim number, command and code item, each byte-for-byte in the chat; correction `old` first appears before `new`; next_step; probes of all 5 kinds | met | `check.py` passes on all 6 files for seeds 7, 8, 0, -3, 1-5 and 1e12. Every verbatim `text` is a substring of some message. Seed 7 correction indexes (first old, first new): coding 8→14, 14→40, 38→80; data_analysis 6→16, 20→46, 38→74. Probe kinds are {fact, decision, verbatim, stale, next_step} in each file. |
| 6. environment categories match the checkpoint workspace categories; repos have branch and last_commit; every status is valid | met | The set of `environment` keys equals `ai_checkpoint.model.WORKSPACE_CATEGORIES`: files, repos, access, connectors, tools, env_vars, skills, references. Repos carry branch and last_commit. Every status is still_relevant or done_with. Env vars are names only. |
| 7. Traps are labelled. Abandoned folder: done_with and not mentioned in the last 25% of messages. Renamed file: old path done_with, new path still_relevant, both in the chat. Secret: `sk-fake-...` appears in the chat, sits in `secret_values`, and is never a manifest name or note | met | `trap` values found: abandoned_folder, renamed_file_old, renamed_file_new and secret_in_chat, one of each per file. Seed 7 abandoned-folder mentions vs the 75% cutoff: coding-100 at [0, 38] (cutoff 75), coding-20 at [0, 8] (cutoff 15), data_analysis-20 at [0, 6] (cutoff 15). The folder's basename, plus words like scratch/sample/download, never appear after the cutoff. The secret value appears nowhere in the file except `messages` and `secret_values`, so it is in no manifest field at all. All of this also holds for seeds 0-5, 8, -3 and 1e12. |
| 8. Placement varies: the correction index differs across the 3 scenarios of a task type, and coding-50 with seeds 1-5 gives at least 3 distinct correction indexes | met | Seed 7 correction (first `new`) indexes: coding 14/40/80, data_analysis 16/46/74. coding-50 with seeds 1-5 gives 36, 38, 40, 46, 44, which is 5 distinct values. |
| 9. Filler varies: no filler text repeats within a scenario, and each 100-message scenario has at least 20 distinct filler messages | met | I identified filler by matching messages against the `fillers.py` pools, independently of `meta`. That found 4/34/84 filler messages, all distinct, so each 100-message file has 84 distinct ones. No message text of any kind repeats in any file. |
| 10. Bad input: `--seed abc` exits 2; an `--out` that is an existing regular file exits 1 with a message and writes nothing | met | `--seed abc` gives rc=2 with "invalid int value: 'abc'", and the out dir is not created. `--out afile`, where afile is an existing file, gives rc=1 with "error: --out afile exists and is not a directory", and afile still contains "hi". |
| 11. Dataset under `datasets/handover-v1/` with a README giving the seed and command; a test regenerates and asserts byte-identical files | met (see note) | The README names seed 7 and `checkpoint-eval generate --seed 7 --out datasets/handover-v1`. `tests/test_dataset.py::test_committed_dataset_is_byte_identical_to_regeneration` compares with `read_bytes()`, and my own regeneration matched too. Note: `datasets/` is still untracked in git, like all of F-001. The orchestrator said this is expected before commit; the commit must include `datasets/`. |
| 12. Old-format scenarios still parse; new optional fields are validated with errors naming the field (`kind: "foo"` gives `probes[0].kind`) | met | Both examples parse unchanged. `kind: "foo"` gives "probes[0].kind: must be one of fact, decision, verbatim, stale, next_step, got 'foo'". I also checked: `answer_key: "x"` gives "answer_key: must be an object", `correction` without `new` gives "answer_key.correction.new: is required", a bad status gives "environment.files[0].status: ...", an unknown category gives "environment.widgets: unknown category", `secret_values: "sk-x"` gives "secret_values: must be a list of strings". |

Test suite: `cd ~/mnt/ai-checkpoint && ~/aic-venv/bin/python -m pytest -q` gave **216 passed** in 36.8s.

## Extra checks
- Unusual seeds: 0, -3, 999999999999 and the default (no `--seed`) all work. With no seed the output equals seed 7. Every criterion check passes for these seeds too. `--seed 1.5` gives rc=2, and a missing `--out` gives rc=2.
- `--out afile/sub`, where afile is a regular file, gives rc=1 with "error: [Errno 20] Not a directory". This is handled cleanly.
- Minor notes, none tied to a criterion:
  - `generate` silently overwrites existing files in `--out`. This is reasonable for a generator, but differs from the planned "refuse to overwrite results.json" rule for `run` and `suite`.
  - Optional string fields inside the environment, such as `repos[].branch: 5`, are not type-checked. They are accepted silently.
  - `probes[].target: ""` is now rejected ("must not be empty") rather than treated as absent. This is a new field, so it is not a regression.
- Cleanup: `git worktree remove --force` refused because the worktree was locked ("initializing"). Git could not unlink its own lock file in the mounted folder because deletion is not permitted there. As a result, `.git/worktrees/qa-wt4/`, which contains `locked` and `HEAD.lock`, is left in the repo's admin directory. I removed the checkout directory `$HOME/qa-wt4` itself; it was outside the mount. Once deletion is allowed in the folder, run `git worktree prune` (or `git worktree remove -f -f`) to clear the leftover entry. Project files are unaffected.

## Regression sweep
`git diff` touches only `src/ai_checkpoint/eval/cli.py` and `src/ai_checkpoint/eval/scenario.py`. The new files are `generate.py`, `fillers.py`, `tests/test_dataset.py` and `datasets/`. The product (save, resume, MCP server, `model.py`) is not touched.

Touched code paths:
- `parse_scenario`, which gained probe `kind` and `target` plus `answer_key`, `environment` and `secret_values`
- `build_parser`, which gained the `generate` subcommand
- `main`, which dispatches to `_generate`

Old code ran from a worktree at HEAD with `PYTHONPATH=$HOME/qa-wt4/src`, and `__file__` confirmed qa-wt4. New code ran from the mount.
- `run` on both example scenarios with `--model fake`: rc=0 for both versions. Output directories and stdout are byte-identical.
- CLI edge cases (no args, `run` with no args, a missing scenario file, `--model bogus`, `run --help`, an unknown subcommand): rc and output are identical. The only difference is that usage and the choices list now include `generate`, which is expected.
- `parse_scenario` on 19 mutated inputs based on invoice-sync. Base file, `kind: "fact"`, `kind: null`, `answer_key: {}`, an extra `meta` key, empty messages, empty probes, empty key_facts, role `system`, and a top-level list all behave the same in both versions. Six inputs changed from accepted (old) to a field-naming error (new): `kind: "foo"`, `target: ""`, `answer_key: "x"`, `correction` missing `new`, a bad environment status or category, and malformed `secret_values`. All six involve the new optional fields that criterion 12 requires to be validated, so none is a regression. No scenario without these keys changed behaviour.

No regressions found.

## Dataset quality note (not a verdict factor)
- **Realism:** The chats read like plausible work sessions. In coding, a Flask webhook service stops sending duplicate SMS. In data analysis, a Q3 churn study is prepared for finance. Messages have pasted code, a raw-body HMAC fix, a warning about the pasted credential, a mid-way correction with a reason ("carrier retries for up to 48 hours", "forgot to exclude is_test accounts"), and an end-of-day recap. Filler is on topic (logging, status codes, timezones, ruff, health checks) and varied.
- **Weaknesses:**
  - The 8 core beats come in a fixed order, and the core wording is the same across lengths and seeds; only names and numbers change. A model that sees several scenarios could learn the template.
  - The next step is always stated in the final message, as a recap. That makes it trivially recent for any recency-based handover.
  - Corrections are always signposted ("One correction...", "A correction to my earlier count").
- **Answerable only from the chat?** Mostly yes:
  - The seeded values can't be guessed: replay tolerance 868/778 seconds, migration 0023/0027, population 50,441, churn rate 0.1259, commit hashes, project and branch names, exact paths.
  - The decisions are somewhat guessable from priors: Postgres-unique over Redis when "no Redis" is stated, ThreadPoolExecutor over Celery, logistic regression over GBTs for finance, and "no payment for N days" churn. A no-handover baseline would probably score partial decision credit, though the exact reasons and rejected options need the chat.
  - The stale value (24 hours) and generic env var names such as `DATABASE_URL` are also fairly guessable.
  - Suggestion: add one non-obvious decision per scenario, for example one where the "usual" option wins for an unusual reason, or the obvious one is rejected.
