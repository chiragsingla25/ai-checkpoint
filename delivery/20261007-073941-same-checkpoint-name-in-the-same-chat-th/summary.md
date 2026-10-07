# Run summary: 20261007-073941-same-checkpoint-name-in-the-same-chat-th

## Request
Same name in the same chat: the first save keeps the name, later saves get Finder-style numbers ('test-v1 (1)', 'test-v1 (2)'), and the save result says the stored name.

## Plan
intake -> build -> qa approved. **QA skipped at Chirag's request**; replaced by a manual smoke check (5 saves + 6 lookups in a scratch store). Builder reported 180 tests passing before the message fix; tests not re-run after it.

## Feature
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Finder-style renumbering of duplicate checkpoint names within a chat | 1 + orchestrator fix | no QA (smoke check OK) | see git log |

Smoke check found one bug: the renumbering message cited the base name's id instead of the id holding the requested name. Fixed in store.py (`clash_id`).

## User-visible changes
- A later save with the same chat + name (case-insensitive) is stored as 'name (N)', lowest free N. Other chats are not renumbered.
- save_checkpoint / `ai-checkpoint save` result adds checkpoint_name, renamed, requested_name, original_id and a message.
- Name refs within a chat now resolve to the earliest save (was newest). Legacy duplicates (cp-001/cp-002 trial/test-v1) are untouched; 'trial/test-v1' now means cp-001. Bare names across chats still pick the newest chat.

## Rulings
None.
