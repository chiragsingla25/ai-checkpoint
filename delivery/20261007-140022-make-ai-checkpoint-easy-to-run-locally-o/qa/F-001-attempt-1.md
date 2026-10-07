VERDICT: PASS

F-001 attempt 1: MCP server instructions that route checkpoint/resume requests to the tools.

Probe method: a scratch script outside the project opened a real stdio MCP session (`python -m ai_checkpoint.server`, cwd=/, PYTHONPATH pointed at the tree under test, AI_CHECKPOINT_HOME=fresh temp dir, GIT_CONFIG_GLOBAL=/dev/null). It called `initialize`, `list_tools`, `list_prompts`, saved two checkpoints (`forecasting/v1`, `trial/test-v1`), then ran list/get/resume over 9 refs plus bad inputs. The same script ran against the working tree and against a `git worktree` of HEAD (125730c).

| Criterion | Result | Evidence |
|---|---|---|
| 1. `initialize` over stdio returns non-empty `instructions` naming `save_checkpoint` and `resume_checkpoint` | met | `init.instructions` (new tree) is a 6-line string, 600+ chars. It contains `save_checkpoint` (line 2) and `resume_checkpoint` (line 3). The new pytest `test_initialize_instructions_route_to_tools` checks the same thing through `ClientSession.initialize()`. |
| 2. Checkpoint/save goes to save_checkpoint. Resume/continue, including a bare `chat/checkpoint` ref like 'resume trial/test-v1', goes to resume_checkpoint and not to files/git/web search | met | Text: "- If the user asks to checkpoint, save or hand over this chat, call save_checkpoint." / "- If the user asks to resume or continue a checkpoint, including a bare ref like 'resume trial/test-v1', call resume_checkpoint with that ref. Do not search files, git or the web for it." Read as a client model would, "resume trial/test-v1" matches that example word for word, and the line names the tool to call and the searches to avoid. Following it works: `resume_checkpoint {"ref":"trial/test-v1"}` returned `is_error=False`, "You are continuing work from checkpoint cp-002 (trial/test-v1) ..." |
| 3. Naming: chat_name is short with no '/', checkpoint_name is short and descriptive (e.g. 'forecasting-v2'), and a 'chat/checkpoint' ref is split into the two parts | met | Text: "- Names: chat_name is a short name for the chat or project, with no '/'. checkpoint_name is a short descriptive name such as 'forecasting-v2'. If the user gives 'chat/checkpoint', split it into those two parts." Following it works: save with chat_name=`trial`, checkpoint_name=`test-v1` returned cp-002. The server still rejects a '/' in chat_name: `chat_name: must not contain '/'`. |
| 4. On resume, read the brief and confirm the current step before continuing. list_checkpoints is mentioned for an unknown/ambiguous ref | met | Text: "- On resume, read the returned brief and confirm the current step with the user before continuing." / "- If the ref is unknown or ambiguous, call list_checkpoints." |
| 5. save_checkpoint description is byte-identical: `SAVE_DESCRIPTION` unchanged and equal to the `list_tools` description | met | `git diff --quiet HEAD -- src/ai_checkpoint/schema.py` gives "unchanged". sha256 of `SAVE_DESCRIPTION` is the same in the new tree, in the HEAD worktree, and in the description returned by `list_tools` over stdio: `38f2a104d749...af52f` (1676 chars) in all three. The new test also asserts `save.description == SAVE_DESCRIPTION`. |
| 6. Full suite passes (110 existing) plus a new initialize-instructions test | met | `python3 -m pytest -q` gives `111 passed in 5.52s` (110 existing + `test_initialize_instructions_route_to_tools`). |

## Extra checks
- Edge inputs over stdio (new tree): `resume_checkpoint ""` gives a tool error "checkpoint not found: empty ref ''". `nope/zzz` and `cp-999` give "checkpoint not found". `save_checkpoint {}` gives a validation error that lists the missing fields. A bare `test-v1` resolves to cp-002. None of these crash the server, and later calls in the same session still succeed. All of these match HEAD.
- The instructions reach both server back-ends: `create_server` passes `instructions=SERVER_INSTRUCTIONS` to `_Server`, which is MCPServer (mcp >= 2) or FastMCP (1.x). Only the string itself changed.
- Note (pre-existing, not caused by this change): when two chats both have a checkpoint named `test-v1`, `GitStore.get('test-v1')` returns one of them ("other") without reporting the ambiguity. The instructions say to call list_checkpoints for ambiguous refs, but the server gives the client no signal that a bare name was ambiguous. A fully qualified `trial/test-v1` resolves correctly. This could become a criterion later if it matters.
- Note: line 3 says to pass "that ref" to resume_checkpoint, and line 4 says to split a 'chat/checkpoint' ref. They do not conflict: splitting applies to the save arguments, and resume takes a single `ref`, which accepts the full `chat/checkpoint` form. A client might still briefly wonder whether it should split on resume as well. Wording such as "when saving, split..." would remove that doubt. This is not required by any criterion.
- Wording difference: the first line changed from "of this chat" to "of a chat". This has no functional effect.

## Regression sweep
Code paths touched (`git diff HEAD`): `SERVER_INSTRUCTIONS` in src/ai_checkpoint/server.py (string only, which feeds `create_server` -> `_Server(..., instructions=)`), and one new test appended to tests/test_server.py. No other functions changed.

Old vs new, same probe against a `git worktree add <scratch>/old HEAD` and the working tree. I normalised timestamps and commit SHAs, then compared 28 outputs:
- `list_tools`: names, descriptions, input schemas and output schemas are identical. The four tools are save_checkpoint, list_checkpoints, get_checkpoint and resume_checkpoint.
- `list_prompts` (the `resume` prompt and its args): identical. `get_prompt resume {ref: trial/test-v1}`: identical.
- save (valid, '/' in chat_name, empty args), list, and get/resume for refs `cp-001`, `forecasting/v1`, `v1`, `trial/test-v1`, `test-v1`, `cp-002`, `""`, `nope/zzz`, `cp-999`: identical. Brief output is unchanged.
- The only difference is `instructions`, which is the intended change.
No regressions found. The worktree was removed (`git worktree remove --force`, `git worktree prune`). The scratch probe files were deleted. Project files were not modified.
