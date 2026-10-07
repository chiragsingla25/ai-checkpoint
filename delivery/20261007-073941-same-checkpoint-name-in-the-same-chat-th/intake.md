# Intake

## Understanding
Saving a checkpoint whose chat_name + checkpoint_name already exists in that chat must no longer create a second checkpoint with the same name. The new save gets the next free Finder-style name ('test-v1 (1)', '(2)', ...), the save result tells the model the stored name and which id holds the original, and name refs to the base name keep pointing at the original (earliest within the chat), including legacy duplicates already on disk.

Class of the problem: name collisions within one chat, under the case-insensitive matching resolve() already uses. Edges: second and third+ collisions; a gap in numbering; the user explicitly giving an already-numbered name that collides; case differences in checkpoint and chat name; collisions with legacy duplicates; the same name in another chat (must not collide); resolution of base and numbered refs with and without chat prefix; cross-chat bare names (unchanged newest-chat-wins). Unchanged inputs: distinct names save and resolve exactly as before; ids remain sequential, files immutable.

## Size
small: one store change (name allocation in save under the existing lock, resolve ordering within a chat), a richer SaveResult, a possible description tweak, and tests.

## Existing project
Python package src/ai_checkpoint (store.py GitStore: save/resolve/list; server.py FastMCP tools + SERVER_INSTRUCTIONS; schema.py SAVE_DESCRIPTION pinned by sha256 in tests/test_eval.py; cli.py prints SaveResult.to_dict()). resolve() currently tries exact chat/name, exact name, then casefolded variants, iterating newest first. SaveResult.to_dict() returns only checkpoint_id and commit. Tests: `cd $HOME/mnt/ai-checkpoint && $HOME/aic-venv/bin/python -m pytest -q` (173 pass). tests/test_store.py lines ~101 and ~130 assert the old newest-wins behaviour and will need updating.

## Recommended stages
build, qa. Behaviour change in an existing store with clear acceptance criteria; no design or research needed.

## Assumptions
- Name allocation happens inside the existing save lock so concurrent saves cannot pick the same number.
- "Next free" means the lowest n >= 1 such that 'base (n)' is not taken (case-insensitive) in that chat, not count+1.
- A requested name that already ends in ' (N)' and collides is treated as base + suffix: the suffix is stripped and the next free number for the base is used ('test-v1 (1)' -> 'test-v1 (2)'). If it does not collide it is stored unchanged.
- The user's casing of the requested name is kept; only the suffix is added.
- Chat names are compared case-insensitively (trimmed), consistent with resolve's casefolded chat/name match.
- Within a chat, a name ref returns the earliest (lowest id) match. For bare names matching several chats, the chat of the newest match wins, then the earliest match within that chat. Exact-case matches still take precedence over casefolded ones as today.
- original_id in the save result is the id the base name resolves to in that chat (earliest match).
- resumed_from resolution uses the same new resolve() rules.
- Save result keeps existing keys (checkpoint_id, commit) and adds checkpoint_name, renamed, requested_name, original_id (null when not renamed) and a short message.

## Open questions
