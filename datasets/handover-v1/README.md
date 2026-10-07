# handover-v1

Six synthetic work chats for evaluating AI Checkpoint handovers: two task types
(`coding`, `data_analysis`) x three lengths (20, 50, 100 messages).

Each file is a scenario for `checkpoint-eval`: the conversation, probe questions,
an `answer_key` (decisions with reasons and rejected alternatives, verbatim items,
one corrected value with its stale `old` value, the next step) and an `environment`
manifest (files, repos, access, connectors, tools, env var names, skills, references;
each item `still_relevant` or `done_with`). Traps, labelled with a `trap` field: a folder
used early then abandoned, a file renamed mid-way, and an env var whose fake secret value
(`sk-fake-...`, listed in `secret_values`) appears in the chat. The `meta` block records
where the planted turns sit (message indexes).

Generated with seed 7, no model needed:

```
checkpoint-eval generate --seed 7 --out datasets/handover-v1
```

Output is deterministic: the same seed always gives byte-identical files (a test
regenerates the dataset and compares). Do not edit the JSON by hand; change the
generator (`src/ai_checkpoint/eval/generate.py`) and regenerate.

Run one scenario offline:

```
checkpoint-eval run datasets/handover-v1/coding-50.json --model fake --out results/coding-50
```
