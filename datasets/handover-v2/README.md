# handover-v2

Same six synthetic work chats as handover-v1 (`coding`, `data_analysis` x 20, 50, 100 messages),
same storylines, traps, probes and random draws, with the dataset bugs found in the first real run fixed:
every probe key fact, decision (with its reason and rejected option), verbatim item, manifest item
(including `ANALYTICS_DB_PATH` and the `Carrier webhook docs` reference), env var name and fake secret is now
stated in the chat in the same words the answer key uses. The generator's self-check
(`check_scenario` in `src/ai_checkpoint/eval/generate.py`) returns an empty list for all six files, and a test enforces it.
`meta.generator` is `handover-v2`. `datasets/handover-v1` is unchanged so the first run stays reproducible.

Generated with seed 7, no model needed:

```
checkpoint-eval generate --seed 7 --version handover-v2 --out datasets/handover-v2
```

Output is deterministic: a test regenerates the dataset and compares bytes. Do not edit the JSON by hand;
change the generator and regenerate.

Run one scenario offline:

```
checkpoint-eval run datasets/handover-v2/coding-50.json --model fake --out results/v2-coding-50
```
