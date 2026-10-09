# Request

Checkpoint bundle v2 (on branch feature/checkpoint-bundle-v2; push only if evals improve). Goal: raise next-step accuracy (baseline 50% in eval-runs/2026-10-09-handover-v2-haiku) to >=90% without lowering key-fact recall (88%), while keeping everything inside the one MCP server (no model, no key, stdlib only).
Design (write it first as docs/DESIGN-v2.md, then build):
- A checkpoint is stored as a folder bundle under ~/.ai-checkpoint/chats/<chat>/checkpoints/cp-NNN/: manifest.json (id, parent/resumed_from, created_at, client, file hashes), plan.json (tasks: id, text, status todo|in_progress|done, from user|ai, quote = user's exact words for user tasks, depends_on, order), decisions.jsonl (decision, reason, rejected[], status active|superseded, supersedes), facts.jsonl (key, value, superseded_by/valid_from), workspace.json, user_turns.jsonl (the user's key messages verbatim), verbatim/ (exact snippets as real files), open_questions.json incl. waiting_on_user, brief.md (rendered, never the source of truth). Per chat an append-only events.jsonl. One git commit per save as today. Ids stay global and sequential (cp-NNN); refs and renumbering behave as today.
- save_checkpoint gains structured fields for the above (old fields still accepted). The server assigns task ids, splits into files, computes the next action (first todo whose deps are done) and renders brief.md opening with 'Next action' and the user's own plan.
- Code checks on save, returned as clear errors so the chat model fixes the save in the same turn: every from=user task quote must appear verbatim in user_turns or last_exchange.user; at least one unfinished task; decisions with discussed alternatives fill rejected; secrets still redacted everywhere.
- Save result echoes the computed next action ('Next action saved: ... Correct?').
- Saving from a resumed chat: the brief shows task ids; save accepts plan updates by id (status changes, new tasks) carried forward from the parent checkpoint instead of rewriting.
- Brief also lists done-with workspace items under 'No longer needed'.
- Old single-file checkpoints keep loading and resuming byte-identically (golden test).
- Eval: the compaction prompt uses the new tool schema; add the bundle path so checkpoint-eval suite on datasets/handover-v2 measures it; FakeModel supports it offline.
Out of scope for now: SQLite search index and ask_checkpoint, embeddings, MCP sampling, online backends.
