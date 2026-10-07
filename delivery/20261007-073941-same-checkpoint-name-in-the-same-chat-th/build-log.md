
## F-001 attempt 1
- What changed: src/ai_checkpoint/store.py (GitStore._unique_name allocates Finder-style names under the save lock; resolve() returns earliest match within the chat of the newest match; SaveResult gains renamed/requested_name/original_id and to_dict adds checkpoint_name, renamed, requested_name, original_id, message). tests/test_store.py: two newest-wins tests updated with comments; 7 new tests for the criteria.
- How to run it: ai-checkpoint save (or the save_checkpoint MCP tool) with a repeated chat/name.
- Tests: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q` -> 180 passed.
- User-visible changes: save result JSON has new keys (checkpoint_name, renamed, requested_name, original_id, message); duplicate names are stored with " (N)" suffix; bare name refs now resolve to the earliest match in a chat.
- Notes: SAVE_DESCRIPTION and server instructions unchanged (result message tells the model), so the pinned hash is untouched. Chat/name trimmed on comparison. original_id falls back to the holder of the requested name if the base name does not exist.

## F-001 fix by orchestrator (after smoke check)
- What changed: src/ai_checkpoint/store.py — the save message now names the id that already holds the *requested* name (new `clash_id`), e.g. saving 'test-v1 (1)' when it exists cites cp-002, not cp-001. `original_id` unchanged (id of the base name).
- Tests: not re-run (user asked for a smoke check only).
- User-visible changes: corrected id in the renumbering message.
