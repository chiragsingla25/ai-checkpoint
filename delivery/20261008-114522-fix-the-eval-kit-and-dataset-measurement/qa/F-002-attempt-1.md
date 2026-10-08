VERDICT: PASS

F-002 attempt 1 is checked against HEAD 4bc1f4b (F-001 committed). All 4 criteria are met.

The only changes in the working tree are src/ai_checkpoint/eval/pipeline.py, the new tests/test_retry.py and build-log.md.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | answer_probes: a reply with 12 answers, then one with 11, gives 11 answers and no errors. The model is called exactly twice, and the second call includes the first reply plus an instruction naming 11 | met | I used my own scripted model with replies `[12 items, 11 items]`. The result is a0..a10 with no errors, and there were 2 calls. The second call's roles are `user, assistant, user`, and the assistant content is byte-equal to the first reply. The last user message reads "Your reply had 12 entries but exactly 11 are expected (one per item in the same order). Reply again with ONLY a JSON array of exactly 11 strings." The mirror cases also recover in 2 calls: too few (10 then 11) and empty (`[]` then 11). The old code (HEAD via git archive, module path confirmed) makes 1 call and errors. |
| 2 | A retry that is also wrong gives the existing error for every probe, with M taken from the retry, after exactly 2 calls | met | Replies of `[12, 13]` give 2 calls, and all 11 probes get `answer reply unusable: expected 11 answers, got 13`. |
| 3 | judge_answers behaves the same way | met | Verdict counts `[2, 3]` for 3 probes give 2 calls with all errors None, and the retry instruction contains "3". Counts `[4, 1]` give 2 calls and `judge reply unusable: expected 3 verdicts, got 1` on every probe. |
| 4 | A right count makes exactly 1 call; unparseable JSON keeps its current handling; the full FakeModel suite passes | met | A right count makes 1 call for both answer and judge. `{oops` and `{"a":1}` each make 1 call and give the same "no JSON array found" error as before. A non-string item still gives a per-item "entry is not text" error after 1 call. `cd ~/mnt/ai-checkpoint && ~/aic-venv/bin/python -m pytest -q` gives 302 passed. |

## Extra checks
- **Byte-identical well-formed runs.** I ran `checkpoint-eval suite datasets/handover-v1/*.json --out ...` with FakeModel and no API keys, at `--workers 1` and `--workers 8`, using both the new code and the old code (HEAD, run with PYTHONPATH=~/qa-old/src). In both cases, `diff -r` of the output folders between old and new was empty: results.json, results.md, handover_*.md and checkpoint.json are all identical. The new progress output has exactly 48 `/8]` lines (8 calls x 6 scenarios) and no "retry" lines.
- **Parallel retries.** I ran `suite` on all 6 v1 scenarios with `--workers 8`, using a FakeModel wrapper that adds one extra item to every first answer and judge reply.
  - It exited 0 with 84 calls: 48 normal and 36 corrective retries (6 variant calls per scenario x 6 scenarios). The retries recovered all 36 replies, and every probe ended with no error.
  - Each results.json is identical to the clean `--workers 8` run except the `model` field ("bad" vs "fake").
  - The progress counter grows correctly when lines interleave (e.g. coding-20 ends `[14/14]`).
- **Retry call fails** (ModelError on both of its attempts): this is handled. The first reply's error, `expected 11 answers, got 12`, is recorded, and the variant does not fail. There were 3 model calls (1 + 2 attempts of the retry).
- **Retry reply is unparseable:** the probes get the parse error ("no JSON array found"), not the count error.

## Regression sweep
**Code paths touched:**
- `Caller.expect_extra_call` (new)
- `_list_with_count_retry` (new)
- `answer_probes` and `judge_answers`, which now delegate to the retry helper

**Old vs new, same inputs:**
- Right-count replies, unparseable replies and non-list JSON give the same output and the same number of calls.
- A full FakeModel suite at workers 1 and 8 gives byte-identical output folders.
- The only behaviour change is a wrong-count reply, which the criteria require.

There were no differences beyond that.

**Notes, not failures:**
1. In a scenario with a retry, progress lines printed before the retry keep "/8" while later lines show "/9" or more. The builder documented this.
2. When a retry's own call fails, the error recorded is the first reply's count error, and the CallFailed itself is not surfaced in results.json. Only the progress line ("FAILED after 2 attempts") shows it. This is reasonable, but a reader of results.json cannot tell that a retry was attempted.
