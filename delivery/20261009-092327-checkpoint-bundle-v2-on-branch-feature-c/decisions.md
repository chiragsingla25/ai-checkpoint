# Decisions (Chirag, at the approval gate)

1. Eval: when save checks reject a checkpoint, give the model ONE retry with the error messages (mirrors the in-chat fix-in-the-same-turn flow). Record whether the retry was needed in results.json.
2. Quote check: case-, whitespace- and punctuation-insensitive match of the user's quote against user_turns / last_exchange.user (same words required).
3. get_checkpoint on a bundle returns BOTH the new structured fields and the old flat fields.
4. A resumed chat saved under a different chat_name goes into the NEW name's chat folder, linked to its parent via resumed_from / manifest parent.
Plan approved as written: 6 features on branch feature/checkpoint-bundle-v2; push only if the real eval improves.

## F-001 amendment rulings (orchestrator, technical; reported to Chirag)
- QA's design review found gaps; resolved in DESIGN-v2.md: id scan includes git history and bundles; chat folder = slug + hash with chat.json and suffix on collision; the free-text "alternatives not recorded" check is dropped (false positives) and checks apply only to new/changed items; task ids continue from the lineage max; first-save rollback removes new files.
- features.json F-004 criteria 0, 1 and 3 updated to match decisions.md ruling 2 and the dropped heuristic.

## F-002 criterion on commit contents (QA objection, attempt 1)
- Ruling (orchestrator, follows the F-001 amendment; reported to Chirag): the first save of a chat also commits chat.json. Criterion reworded accordingly. Does not count as an attempt.

## F-003 task numbering on resumed saves (QA finding, attempt 1)
- Ruling (orchestrator, technical; reported to Chirag): in a fresh `tasks` list, `depends_on` is read positionally — `t-k` means the k-th item of THIS list — and the server rewrites it to the id actually assigned (t-(N+k), continuing from the lineage max). Ids are never reused. DESIGN-v2 §7's sentence "depends_on refers to tasks in the same list by the id they will receive" is replaced accordingly, and SAVE_DESCRIPTION says "the server numbers them for you; in depends_on, task k of your list is t-k".
- Reason: a small model following the tool text must get the dependencies it meant; positional ids need no knowledge of the parent's highest id.

## F-005 criterion 4 scope (QA objection, attempt 1)
- Question: do old-fields-only resumed saves carry forward unmentioned parent sections?
- Ruling (orchestrator, follows the approved request "saving from a resumed chat ... carried forward from the parent checkpoint instead of rewriting"; reported to Chirag): YES — every save with resumed_from carries forward the sections it does not supply, whatever field style it uses. Sections it does supply replace the parent's. Does not count as an attempt.
- Also fix: in `plan_updates`, depends_on text must state that ids refer to the real task ids shown in the brief (e.g. [t-3]), not list positions, so the model can't silently get a wrong dependency.
- Clarification on duplicates (QA trade-off): for an old-fields-only resumed save, a section it supplies REPLACES the parent's section wholesale (no merge, so restated decisions are not duplicated); sections it omits are carried. Structured saves keep the DESIGN-v2 merge behaviour.

## F-005 criterion 4 — ruling by Chirag (2026-10-10), overrides the orchestrator's ruling above
- Ruling: option (a). Carry-forward applies only to resumed saves that use the structured fields (tasks, plan_updates, user_turns or facts). An old-fields-only resumed save behaves as before: nothing is carried.
- Reason: owner's call; keeps old-style saves unchanged and steers resumed chats to the new style.
- Effect: criterion 4 reworded to QA's proposed wording (a) in features.json. The builder's attempt 1 already implements (a), so no code change is needed for this criterion. The orchestrator's "carry for every resumed save" ruling and its old-fields replace-wholesale clarification are withdrawn.
- Still open from the orchestrator's entry: its extra request that the plan_updates depends_on text say ids are the real task ids shown in the brief. That is not a written criterion; QA should treat it as a Note unless Chirag adopts it.

## F-005 plan_updates depends_on description (QA note, attempt 1) — ruling by Chirag (2026-10-10)
- Objection/note by QA: `plan_updates[].depends_on` reuses the `tasks` text ("Task k in your list is t-k"), but plan_updates ids are real lineage ids, so a model following the text can get a silently wrong dependency.
- Ruling: fix it. New criterion 7 added to F-005: plan_updates depends_on has its own description (real ids from the brief, not positions).
- Reason: same class of silent-wrong-dependency problem as F-003 attempt 1.
- Effect: F-005 goes back to the builder (attempt 2), then a QA re-check.

## Correction (orchestrator, 2026-10-10)
- The statement above that "attempt 1 already implements (a)" was wrong. QA re-check (qa/F-005-attempt-2.md) found that the code committed as 9107b1e carries forward for every resumed save (`carry = parent_v2 is not None`). That is the withdrawn orchestrator ruling. The working tree had been changed after attempt-1 QA without a build-log entry, and the orchestrator committed it without re-verifying. F-005 goes back to the builder (attempt 3) to implement Chirag's ruling (a).
