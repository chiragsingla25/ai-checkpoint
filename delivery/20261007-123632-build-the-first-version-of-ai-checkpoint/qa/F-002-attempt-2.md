VERDICT: FAIL

QA for F-002 (Local stdio MCP server, resume brief and thin CLI), attempt 2. Code under test is the uncommitted working tree on top of 549fcb1 (F-001). Every run used a fresh temporary `AI_CHECKPOINT_HOME`. Installed `mcp` is 2.2.0. Scratch scripts were in the session scratchpad, not the project.

Result: all 10 criteria are met as written, including the attempt-1 failure (criterion 9). The verdict is FAIL because of a regression in F-001 store behaviour: the new non-Mapping guard in `GitStore.save` rejects two inputs that F-001 saved successfully. The case is narrow and the fix is one line. See "Regression sweep" and "For the builder".

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | stdio server via console script and `python -m`; list_tools and list_prompts | met | My own `ClientSession` over `stdio_client` ran against `ai-checkpoint-mcp` and `python3 -m ai_checkpoint.server` with `AI_CHECKPOINT_HOME=<mkdtemp>`. Both returned `server: ai-checkpoint`, `tools: ['get_checkpoint', 'list_checkpoints', 'resume_checkpoint', 'save_checkpoint']` (exactly four) and `prompts: [('resume', [('ref', True)])]`. `tests/test_server.py::test_stdio_session_end_to_end` launches the server as a subprocess with `AI_CHECKPOINT_HOME` set. |
| 2 | save_checkpoint schema documents every section | met | Over stdio, `required: ['chat_name', 'checkpoint_name', 'objective', 'current_step', 'next_steps']`. The schema has 14 properties, and `props w/o desc: []`. client and resumed_from are optional. The tool description is 1676 chars and holds the compaction instructions. |
| 3 | stdio round trip | met | `save_checkpoint` gave `is_error False`, `{'checkpoint_id': 'cp-001', 'commit': '0277ad04…'}` (structured content and text). `list_checkpoints` listed cp-001 with `brief_tokens: 382`. `get_checkpoint("sales-forecast/forecasting-v2")` returned verbatim content equal to the input (`True`). `resume_checkpoint` by `cp-001` and by `forecasting-v2` gave identical text. `get_prompt('resume', {'ref':'cp-001'})` returned 1 message, role `user`, and its text `==` the resume_checkpoint output (`True`). |
| 4 | in-process tools; invalid input gives isError naming the problem; server keeps running | met | In-process with `mcp.Client(create_server(GitStore(tmp)))`: missing objective gave `True` "objective Field required". Empty next_steps gave `True` "next_steps: must not be empty". `next_steps:["  "]` gave `True` "next_steps[0]: must not be empty". `resumed_from:"cp-9"` gave `True` "resumed_from: no checkpoint matches 'cp-9'". get `zz` gave `True` "checkpoint not found: 'zz'". get `""` gave `True` "checkpoint not found: empty ref ''". A valid save afterwards gave `is_error False` cp-001. Over stdio the messages and flags were the same, and a following valid save returned cp-002. |
| 5 | brief deterministic, header, fixed order, empty sections, closing instruction | met | Repeated resume calls gave identical text. The first line reads "You are continuing work from checkpoint cp-001 (sales-forecast/forecasting-v2), saved 2026-10-07T01:48:59Z in claude-code." The headings are Objective, Context, Decisions already made, Completed so far, Current step, Next steps, Open questions, Verbatim material, Last exchange, Notes from the previous AI, Before you continue. In a minimal checkpoint, every empty optional section shows `_(none recorded)_` and the headings stay the same. The brief ends with "…Ask them to confirm or correct that before you carry on. Then continue from the current step." |
| 6 | verbatim fenced with label, byte for byte, fence longer than any run | met | Stdio content ``"def f():\n\t```py\n  x = '`'  ``  `````\n\tnaïve ☃ 日本語  \n"`` sits under `**model call**` in a 6-backtick fence. The regex `\*\*model call\*\*\n+(`{3,})\n(.*?)\n\1\n` extracts it equal to the input. In-process checks also extracted these byte for byte: ``"````"``, `"\n\nlead\n"`, `"a\r\nb\r\n"`, ``"```\n```"``, ``"end`"``, `"\t​😀 x "`. All returned True. |
| 7 | last_exchange word for word | met | User text ``ok try `(2,1,1)` next — and show MAPE`` and the assistant text (which contains a ``` fence) are both exact substrings of the brief (`True True`). |
| 8 | get and list include a brief size estimate | met | `get_checkpoint` gives `brief_chars 1527` and `brief_tokens 382`, and `ceil(1527/4)==382` is True. `list_checkpoints` entries carry `brief_tokens`. CLI `list` shows `~382 tokens`. The chars/4 heuristic is documented in the README, the tool docstrings and brief.py. |
| 9 | thin CLI; resume matches MCP; clean errors | met | `ai-checkpoint save --file cp.json` returned rc 0 cp-003. `save --file -` from stdin returned rc 0. `list`, `python3 -m ai_checkpoint list --chat nope` ("no checkpoints", rc 0) and `get cp-1` (JSON with brief_tokens) all worked. `ai-checkpoint resume forecasting-v2` output `==` MCP resume_checkpoint text: True. **The attempt-1 failure is fixed.** Piping `"str"`, `null`, `5`, `[1]`, `[]`, `true` and `1.5` to `save --file -` each gives `error: stdin must contain a JSON object (got <type>)` with rc 1 and no traceback. `save --file arr.json` containing `[1]` gives `error: arr.json must contain a JSON object (got list)` with an empty stdout. These are also clean with rc 1: missing file, invalid JSON, non-UTF-8 bytes, a directory, missing field, wrong type (`next_steps: must be a list of strings, got str`), 100k-deep nested arrays (`deep.json is nested too deeply`), empty stdin, `get zz`, `resume zz`, `resume ''` and `get cp-999`. Errors go to stderr. Argparse usage errors exit 2. |
| 10 | README install and mcpServers registration | met | README has `pip install -e .[mcp]`, an `"mcpServers": {"ai-checkpoint": {"command": "ai-checkpoint-mcp", "env": {"AI_CHECKPOINT_HOME": …}}}` example, the `python3 -m ai_checkpoint.server` alternative, and `claude mcp add ai-checkpoint --env AI_CHECKPOINT_HOME=… -- ai-checkpoint-mcp`. |

Test suite: `python3 -m pytest -q` gave 65 passed in 3.81s. The F-001 suite from the HEAD worktree (38 tests), run against the new `src`, gave 38 passed.

## Extra checks
These are notes only and do not affect the verdict.
- **The `resume` prompt with an unknown ref** still fails as a JSON-RPC `MCPError` with only the text "Error rendering prompt resume". The server logs a traceback to stderr. A user who mistypes a ref when picking the prompt gets no reason. Criterion 4 covers tools only. This finding is carried over from attempt 1.
- **Server state after the failed prompt call.** After that `get_prompt`, `list_checkpoints` still returned `is_error False`, so the server kept running.
- **Unwrapped errors in the CLI handler.** The new last-resort handler prints `error: ValueError: …` for unexpected ValueError, TypeError and KeyError. That avoids tracebacks, but it can also hide real bugs. It is acceptable for a thin CLI.
- **Inconsistent stream naming.** The non-object message says "stdin", but the invalid-JSON message for stdin says `- is not valid JSON`. `null` is reported as "got NoneType" rather than "got null". Both are cosmetic.
- **Unusable store path.** `AI_CHECKPOINT_HOME=/proc/nope ai-checkpoint list` still prints "no checkpoints" with rc 0. Carried over.
- **Duplicate saves.** Saving the same cp.json twice gives cp-003 and then cp-004. This is intended F-001 immutability.
- **In-process tests.** They still assert `ToolError` from `server.call_tool`, not `isError`. I checked `is_error=True` directly through `mcp.Client(server)`.
- **Untested `mcp` 1.x fallback.** `pyproject.toml` still declares `mcp>=1.2`, and the 1.x fallback is untested.

## Regression sweep
Code paths changed since attempt 1: `cli.py` (`_run` save branch and `main` exception handling), and `store.py` `GitStore.save` (the first lines, which replace `dict(data)` with a Checkpoint/Mapping/else-raise branch). Unchanged from attempt 1: `brief.py`, `server.py` and `pyproject.toml` scripts. `GitStore.list` calls `render_brief`.

Method: `git worktree add <scratch>/old HEAD` (F-001). The same script ran against both `src` trees with a fixed clock and a fresh store. It saved: a plain dict; a dict with verbatim, decisions and a `password=` secret; an `OrderedDict`; a `MappingProxyType`; a duck-typed mapping (`keys()` + `__getitem__`, not a registered `Mapping`); a list of `(key, value)` pairs; a `Checkpoint` object; resumed_from `cp-1`; unknown keys; null optionals; and the invalid inputs (empty next_steps, unknown resumed_from, `/` in chat_name, missing or blank objective, a `cp-005` name, `{}`, `None`, `"x"`, `5`, `[1]`, `[]`, `b"ab"`). Then `get` on 15 refs and `list` for None, `c`, `zzz` and `""`.

Differences:
- **Regression.** These two inputs saved successfully in F-001 and now raise `ValidationError: checkpoint: must be an object (got …)`:
  - Duck-typed mapping: old returned `ok cp-005`. New gives `got Duck`.
  - `list({...}.items())`: old returned `ok cp-006`. New gives `got list`.
- Intended or improved. These used to crash and now raise a clean `ValidationError`: `None` (old TypeError), `"x"` (old ValueError), `5` and `[1]` (old TypeError), `b"ab"` (old TypeError).
- `[]` changed from "chat_name: is required" to "checkpoint: must be an object (got list)". This is the message attempt 1 asked for.
- Every other difference is an id shift caused by the two rejected saves, or a `brief_tokens` value. I excluded `brief_tokens` because that change was reviewed in attempt 1 and is intended. The plain dict, OrderedDict, MappingProxy, Checkpoint, resumed_from and redaction paths gave identical output.

The worktree was removed. `git worktree list` shows only the main tree. My temp stores were deleted.

## For the builder (FAIL only)
1. **`GitStore.save` rejects inputs that F-001 accepted.** This is a regression in F-001 behaviour, not an F-002 criterion. Reproduce:
   ```
   PYTHONPATH=src python3 -c "
   import tempfile; from ai_checkpoint.store import GitStore
   s = GitStore(tempfile.mkdtemp())
   d = {'chat_name':'c','checkpoint_name':'n','objective':'o','current_step':'s','next_steps':['a']}
   class Duck:
       def keys(self): return d.keys()
       def __getitem__(self, k): return d[k]
   print(s.save(list(d.items())))   # F-001: SaveResult cp-001; now ValidationError (got list)
   print(s.save(Duck()))            # F-001: SaveResult;        now ValidationError (got Duck)
   "
   ```
   Correct behaviour: anything `dict()` accepted before still saves, and only input that `dict()` cannot convert becomes a `ValidationError`. For example:
   ```python
   if isinstance(data, Checkpoint): raw = data.to_dict()
   else:
       try: raw = dict(data)
       except (TypeError, ValueError):
           raise ValidationError("checkpoint", f"must be an object (got {type(data).__name__})")
   ```
   The CLI already rejects non-object JSON itself, so its messages for `[1]` and `[]` stay as they are now. In the store, `[]` would go back to "chat_name: is required", which is the F-001 behaviour. Update `test_store_rejects_non_mapping` (or the equivalent) to match, and add a store test that saves a list of pairs.

   If the owner instead decides that `save` should accept only `Mapping` or `Checkpoint`, as the type hint says, the orchestrator should record that ruling, and this item can be closed without a code change.
