# Decisions (Chirag, at the approval gate)

1. Eval: when save checks reject a checkpoint, give the model ONE retry with the error messages (mirrors the in-chat fix-in-the-same-turn flow). Record whether the retry was needed in results.json.
2. Quote check: case-, whitespace- and punctuation-insensitive match of the user's quote against user_turns / last_exchange.user (same words required).
3. get_checkpoint on a bundle returns BOTH the new structured fields and the old flat fields.
4. A resumed chat saved under a different chat_name goes into the NEW name's chat folder, linked to its parent via resumed_from / manifest parent.
Plan approved as written: 6 features on branch feature/checkpoint-bundle-v2; push only if the real eval improves.

## F-001 amendment rulings (orchestrator, technical; reported to Chirag)
- QA's design review found gaps; resolved in DESIGN-v2.md: id scan includes git history and bundles; chat folder = slug + hash with chat.json and suffix on collision; the free-text "alternatives not recorded" check is dropped (false positives) and checks apply only to new/changed items; task ids continue from the lineage max; first-save rollback removes new files.
- features.json F-004 criteria 0, 1 and 3 updated to match decisions.md ruling 2 and the dropped heuristic.
