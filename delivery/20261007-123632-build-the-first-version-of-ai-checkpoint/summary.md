# Run summary: 20261007-123632-build-the-first-version-of-ai-checkpoint

## Request
First version of AI Checkpoint per docs/IDEA.md: checkpoint format + git storage, local MCP server + resume brief + CLI, handover evaluation kit. docs/ROADMAP.md out of scope.

## Plan
intake -> build -> qa (per feature). Reason: new package with storage-integrity, MCP-protocol and eval-scoring criteria; QA verifies each independently.

## Features
| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Checkpoint format, validation and git-backed local storage | 1 | PASS (11/11) | 549fcb1 |
| F-002 Local stdio MCP server, resume brief and thin CLI | 3 | PASS (10/10) | f9d9510 |
| F-003 Handover evaluation kit | 2 | PASS (9/9) | 8b03f46 |

F-002 fails: (1) CLI traceback on valid-but-non-object JSON; (2) the fix over-tightened GitStore.save and rejected list-of-pairs input F-001 accepted (regression), fixed by normalising via dict().
F-003 fail: save_checkpoint tool description lost one blank line when moved to schema.py; now pinned by a hash test.

## Rulings
None (no objections). Before the build the user refined the idea (model-authored compaction via MCP instead of transcript capture/hooks); the first run was superseded with nothing built.

## User-visible changes
- New commands: `ai-checkpoint` (save/list/get/resume), `ai-checkpoint-mcp`, `checkpoint-eval`.
- `get_checkpoint` output includes `brief_chars` and `brief_tokens` (chars/4 heuristic).
- Store at ~/.ai-checkpoint (override AI_CHECKPOINT_HOME), git commit per save, secret patterns redacted.

## Known gaps (notes from QA/build, not failures)
- Anthropic/OpenAI eval adapters tested only against stub SDKs (no API keys in the sandbox). Default models claude-sonnet-5-5 / gpt-5, overridable.
- FakeModel eval scores exercise the pipeline only; they are not results.
- `resume` prompt with an unknown ref returns a generic SDK error; mcp 1.x fallback import untested (built on mcp 2.2).
- Double space in brief header when a checkpoint has no id (eval-only path).
