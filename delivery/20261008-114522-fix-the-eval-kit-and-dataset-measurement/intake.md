# Intake

## Understanding
The first real run (results/handover-v1-haiku, Claude Haiku 5.5) exposed measurement bugs in the eval kit and the dataset, not in the product. Fix the code-scored metrics, add one corrective retry for batched replies, fix the dataset generator so every key fact is actually in the chat, ship datasets/handover-v2, and add a `rescore` command so the existing run can be rescored with no model calls. Product code (save/resume/MCP/schema, anything in src/ai_checkpoint/ outside eval/) must not change.

Bug classes and their edges:
- Stale scorer: "old value mentioned anywhere = stale". Real class: answers that give the new value as current and mention the old one as history (replaced / earlier / superseded / was wrong / still says, needs updating, including old SQL quoted as the draft). In the Haiku run 13 of 15 scored stale answers were false positives; none of the 15 was genuinely stale. Edges: old only (1), old first and new negated ("24 hours, not 48") (1), new only (0), neither (0), old as history before new (0), old inside new (existing rule, 0).
- Workspace matcher: exact same-category key equality. Edges: relative vs absolute paths (segment-boundary suffix only, not substrings like data/raw vs mydata/raw or raw2), same path filed under repos vs access vs files, and recall split by status. The brief's "Set up first" only renders still_relevant items, so done_with recall from a brief is 0 by construction; the split makes that visible.
- Next-step scorer: literal substring of required terms. Edge: a filename term vs its stem/number (0023 matches, 0029/00230/10023 must not); strict mode keeps the old behaviour. Only the coding-20 checkpoint answer flips; five other 0s are genuine misses and must stay 0.
- Batched replies: count mismatch (coding-50 checkpoint: 12 answers for 11 questions) turns all probes into errors. Edges: fixed on retry, wrong twice, right first time.
- Dataset: generator plants manifest/answer-key items it never states in chat (ANALYTICS_DB_PATH in data_analysis, "Carrier webhook docs" in coding, decision reasons paraphrased).

## Size
medium; three separable pieces touching metrics.py, pipeline.py, cli.py, report.py and generate.py, each well specified with real examples, no product changes.

## Existing project
Python package at $HOME/mnt/ai-checkpoint, eval kit in src/ai_checkpoint/eval/ (metrics.py 142 lines, pipeline.py 394, cli.py 166, generate.py 419, report.py 66). Tests: `$HOME/aic-venv/bin/python -m pytest -q` (282 pass); tests/fixtures exists. datasets/handover-v1 is generated with seed 7 from an RNG string "handover-v1|seed|task|length", and tests/test_dataset.py asserts the committed files are byte-identical to regeneration. results/ is gitignored; results.json per scenario holds answers per variant (no probe kind/target, so rescore needs the scenario file) and the brief as handover_checkpoint.md; the checkpoint JSON itself (workspace) is NOT saved, so the Haiku run's workspace can only be rescored from the brief's "Set up first" section.

## Recommended stages
build, qa. Build in order F-001 (scorers + rescore), F-002 (retry), F-003 (generator + v2). QA can verify everything offline with FakeModel and the fixtures.

## Assumptions
- Stale rule: score 1 when the old value is present and either the new value is absent or the old value is the one presented as the answer (appears first and is not framed as history); 0 otherwise. Exact history-cue wording is the builder's choice as long as the listed cases hold.
- Cross-category matching (files/repos/access) counts for recall only; precision and status accuracy use matched pairs as before. One checkpoint item may satisfy both the repos and access manifest entries for the same path.
- Rescore never overwrites results.json; it writes rescored.json per scenario folder. --dataset defaults to datasets/handover-v1, scenario looked up by results.json "scenario". Future runs additionally save checkpoint.json (eval/report.py only) so workspace rescoring is exact; old runs fall back to parsing the brief and say so.
- Retry covers item-count mismatch only (as requested); unparseable JSON keeps current handling.
- Generator gets a version switch (handover-v1 reproduces the old bytes, handover-v2 is the fixed one, default handover-v2); v2 uses seed 7.
- Self-check uses case-insensitive substring presence in the concatenated chat text; v2 states decision reasons in the same words as the answer key.

## Open questions
