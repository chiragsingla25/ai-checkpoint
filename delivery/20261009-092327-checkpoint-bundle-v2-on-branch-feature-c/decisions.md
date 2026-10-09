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
