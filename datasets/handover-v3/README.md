# handover-v3

Eleven human conversations from [OpenAssistant/oasst1](https://huggingface.co/datasets/OpenAssistant/oasst1)
(Apache-2.0, export `2023-04-12`). The message text is the thread as published.
Nothing is padded out to 20, 50, or 100 turns, and no secret is planted.

Subjects: coding, data_analysis, writing, literature, housing, manufacturing,
engineering, games, geography, hardware, learning.

`sources/oasst1_threads.json` holds the threads (message ids, no user ids).
The answer key only uses phrases that already appear in the thread. A test
regenerates the scenario files and compares bytes.

Download the trees this excerpt came from:

```
hf download OpenAssistant/oasst1 2023-04-12_oasst_ready.trees.jsonl.gz --repo-type dataset
```

Regenerate the scenario files (the conversations do not depend on the seed):

```
checkpoint-eval generate --seed 7 --version handover-v3 --out datasets/handover-v3
```

Run one scenario offline:

```
checkpoint-eval run datasets/handover-v3/coding.json --model fake --out results/v3-coding
```
