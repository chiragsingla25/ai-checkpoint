VERDICT: PASS

F-003 attempt 1 was checked against HEAD 03746be, with F-001 and F-002 already committed. All 7 criteria are met.

Working-tree changes: generate.py, cli.py, tests/test_dataset.py, the new datasets/handover-v2/, and build-log.md.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | The self-check reports every missing probe key_fact, decision reason, next-step term, manifest key (path/name, plus reference name and url), env var and secret | met | `generate.check_scenario` covers probe key_facts, each decision's decision/reason/rejected, verbatim text, correction old/new, the next-step text and its required_terms, every environment item's path or name, reference urls (env vars are environment.env_vars names), and secret_values. Matching is case-insensitive. **Mutation test:** for each of the 201 distinct items across the six v2 files, I deleted every occurrence of that item from a copy's messages and re-ran the check. All 201 were reported (201/201). **Sentence removal on copies:** (a) Removing the v2 "Agreed: fit a logistic regression... a more complex model would add little." sentence from data_analysis-50 reports decisions[1].decision and reason, plus probes[1].key_facts. (b) Removing the ANALYTICS_DB_PATH clause reports both the env var and probes[10].key_facts. (c) Removing coding-50's "One correction on retention:..." sentence reports 'Carrier webhook docs' and the reference url. **Added unstated items:** a made-up decision reason, an env var NEW_VAR and a secret not in the chat are each reported. |
| 2 | The check on v1 is non-empty, lists ANALYTICS_DB_PATH for every data_analysis scenario and 'Carrier webhook docs' for every coding scenario, and a test asserts this | met | v1 coding-* each have 13 missing items, including `environment.references: Carrier webhook docs`. v1 data_analysis-* each have 11, including `environment.env_vars: ANALYTICS_DB_PATH` and `probes[10].key_facts: ANALYTICS_DB_PATH`. test_self_check_catches_v1_bugs asserts this. |
| 3 | A test generates all 6 v2 scenarios and asserts []; the chats contain the four key phrases | met | The check returns [] for all 6 committed v2 files and in the test. data_analysis chats contain 'ANALYTICS_DB_PATH' and 'finance needs coefficients they can read and explain, and a more complex model would add little'. Coding chats contain 'Carrier webhook docs' and 'a thread pool needs no new infrastructure'. Each phrase is checked against the scenario type it belongs to. |
| 4 | handover-v2 holds the 6 scenarios, meta.generator == 'handover-v2', a README with seed 7 and the command, and byte-identical regeneration | met | All 6 files have generator 'handover-v2'. The README gives `checkpoint-eval generate --seed 7 --version handover-v2 --out datasets/handover-v2`. I ran that command into a scratch folder and `diff -r` against datasets/handover-v2 differs only in the README.md. A test covers this as well. |
| 5 | handover-v1 is unchanged and reproducible; the existing byte-identical test passes | met | `git diff --stat HEAD -- datasets/handover-v1` and `git diff --stat 7e5f662 -- datasets/handover-v1` (before F-001) are both empty. `generate --seed 7 --version handover-v1` and `generate --seed 7` with no flag both reproduce the folder byte-for-byte, except for its README. `git diff tests/test_dataset.py` removes no lines. |
| 6 | `generate --version bogus` exits non-zero and lists the valid versions | met | It exits 2 with `argument --version: invalid choice: 'bogus' (choose from 'handover-v1', 'handover-v2')` and creates no output folder. `--version ""` behaves the same way. `generate_scenario(..., 'handover-v3')` raises ValueError listing both versions. |
| 7 | No src/ai_checkpoint change outside eval/ across all three features; pytest passes with at least 282 tests, offline | met | `git diff --stat 7e5f662 -- src/ai_checkpoint ':!src/ai_checkpoint/eval'` is empty and git status shows nothing there. `~/aic-venv/bin/python -m pytest -q` reports 307 passed. |

## Extra checks
- **v1 against v2, per scenario:** only 3 messages differ in each (the two decision turns and either the correction turn (coding) or the opening turn (data_analysis)). Message counts, probes, answer_key, environment, secret_values and every meta index are identical. Only meta.generator differs, so the trap and correction indexes still line up.
- **Offline run on v2:** `checkpoint-eval suite datasets/handover-v2/*.json --workers 8` with the fake model exits 0.
- **Readability (note only):** the v2 decision turns read somewhat formal and stitched. For example, "Good, Celery is out. Send the notification from a ThreadPoolExecutor(max_workers=8) and return 202 immediately: the carrier retries when the response takes too long, and a thread pool needs no new infrastructure." and "Let's go with this: churn means no successful payment for 45 days." They are still coherent user turns. They also state the answer key nearly word for word, which makes decision probes easier than in v1. Keep this in mind when comparing v1 and v2 scores.
- **Note:** the self-check is a substring presence test. Short items such as required terms ('slide', 'logistic') or a correction value can be satisfied by an unrelated mention. Removing the correction sentence in coding-50 did not flag the new TTL because "48 hours" also appears in the assistant's reply. The check proves each item is mentioned, not that the item is stated in its intended context.
- **Note:** the CLI default is still handover-v1, which the intake suggested changing to v2. No criterion requires the change, and the builder explains the trade-off.
- **Note:** `check_scenario` ignores must_not_contradict and known_wrong. That is correct, since the chat need not state wrong answers, and must_not_contradict is a subset of key_facts here.

## Regression sweep
Code paths touched:
- `generate_scenario` and `generate_dataset` (new `version` parameter, defaulting to v1)
- `_coding_story` and `_data_story` (new `v2` branches)
- the new `check_scenario`
- cli `generate --version`

Old behaviour I compared: the default and `--version handover-v1` outputs are byte-identical to the committed v1 files (the old code's output, since v1 has not changed since 7e5f662), and the existing dataset tests pass unchanged. I found no differences.
