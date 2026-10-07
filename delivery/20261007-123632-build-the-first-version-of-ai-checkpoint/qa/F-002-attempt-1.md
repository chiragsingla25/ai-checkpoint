VERDICT: FAIL

QA for F-002 (Local stdio MCP server, resume brief and thin CLI), attempt 1. Code under test is the uncommitted working tree on top of 549fcb1 (F-001). Every run used a fresh temporary `AI_CHECKPOINT_HOME`. Installed `mcp` is 2.2.0. Scratch scripts were in the session scratchpad and are not in the project.

Result: 9 of 10 criteria met. One is not met: the CLI prints a Python traceback when the `save --file` JSON is valid but is not an object.

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | stdio server via console script and `python -m`; list_tools and list_prompts | met | My own `ClientSession` over `stdio_client` ran against both `ai-checkpoint-mcp` and `python3 -m ai_checkpoint.server`, with `AI_CHECKPOINT_HOME=<mkdtemp>`. Output: `tools: ['get_checkpoint', 'list_checkpoints', 'resume_checkpoint', 'save_checkpoint']` (exactly four) and `prompts: [('resume', [('ref', True)])]`. `server_info.name` is `ai-checkpoint` and the server sends instructions. `tests/test_server.py::test_stdio_session_end_to_end` also launches the server as a subprocess. |
| 2 | save_checkpoint schema documents every section | met | Over stdio, `required: ['chat_name','checkpoint_name','objective','current_step','next_steps']`. All 14 properties have a non-empty description: chat_name, checkpoint_name, objective, current_step, next_steps, context, decisions, completed, open_questions, verbatim, last_exchange, notes_for_next_ai, client, resumed_from. client and resumed_from are optional. The `$defs` DecisionIn, VerbatimIn and LastExchangeIn have field descriptions. The tool description holds the full compaction instructions (whole conversation, verbatim copied character for character, no invention, no secrets). |
| 3 | stdio round trip: save, then list/get/resume/prompt | met | I saved a realistic checkpoint (sales forecast; 2 verbatim items, one holding a triple-backtick run, tabs and unicode; last_exchange with backticks). The result was `{'checkpoint_id': 'cp-001', 'commit': '0e873f3c…'}`, both as structured content and as text. `list_checkpoints` showed cp-001 with `brief_tokens: 466`. `get_checkpoint("sales-forecast/forecasting-v2")` returned every section, and its verbatim content equals the input. `resume_checkpoint` by id and by name gave identical text. `get_prompt('resume', {'ref': 'cp-001'})` returned 1 message with role user, and its text `==` the resume_checkpoint output: True. |
| 4 | in-process tools; invalid input gives isError with a message naming the problem; server keeps running | met | In-process with `mcp.Client(create_server(GitStore(tmp)))` (no subprocess): missing objective gave `is_error=True` and "objective  Field required". Empty next_steps gave True and "next_steps: must not be empty". `resumed_from: cp-9` gave True and "resumed_from: no checkpoint matches 'cp-9'". Unknown ref gave True and "checkpoint not found: 'zz'". A valid save after these returned `is_error=False` cp-001. Over stdio I got the same messages plus `next_steps: ["  "]` giving "next_steps[0]: must not be empty", an empty ref giving "checkpoint not found: empty ref ''", `next_steps: "do it"` giving "Input should be a valid list", and `chat_name: "a/b"` giving "must not contain '/'". All of these had isError True, and a later save succeeded (cp-002). |
| 5 | brief deterministic, header, fixed order, empty sections, closing instruction | met | The two resume calls returned identical text. The header reads "You are continuing work from checkpoint cp-001 (sales-forecast/forecasting-v2), saved 2026-10-07T01:45:35Z in claude-code." The sections appear in the README's order: Objective, Context, Decisions already made, Completed so far, Current step, Next steps, Open questions, Verbatim material, Last exchange, Notes from the previous AI. The brief ends with "## Before you continue … Ask them to confirm or correct that before you carry on." In a checkpoint with no decisions, verbatim or last_exchange, each of those sections showed `_(none recorded)_` and the layout did not change. A checkpoint with resumed_from gets an extra line in the header. The full brief I read is reproduced at the end of this report. |
| 6 | verbatim fenced with label, byte for byte, fence longer than any run | met | The content was ``"def f():\n\t```py\n  x = '`'  ``  `````\n\tnaïve ☃ 日本語  \n"``. It appears under `**model call**` in a 6-backtick fence, and extracting it with the regex `\*\*model call\*\*\n(`{3,})\n(.*?)\n\1\n` gives exactly the input. In-process edge cases also extracted byte for byte: ``"````"``, `"\n\nlead\n"`, `"a\r\nb\r\n"`, `"x"`, ``"```\n```"``, ``"end with backtick`"``, and a string with a tab, a zero-width space and an emoji. Whitespace-only content is rejected at save ("verbatim[0].content: must not be empty"), which is F-001 validation. |
| 7 | last_exchange word for word | met | Over stdio, both the user message ``ok try `(2,1,1)` next — and show MAPE`` and the assistant reply (which contains a fenced block) appear as exact substrings of the brief. The assistant reply is in a 4-backtick fence. |
| 8 | get and list include a brief size estimate | met | `get_checkpoint` includes `brief_chars: 1862` and `brief_tokens: 466`, and 466 = ceil(1862/4). `list_checkpoints` entries include `brief_tokens`. The heuristic is documented in the README, the tool docstrings and the brief.py docstring. |
| 9 | thin CLI: save/list/get/resume; resume matches MCP; clean errors | **not met** | These work: `ai-checkpoint save --file cp.json` (rc 0, id and commit), `python3 -m ai_checkpoint list`, `list --chat sales-forecast`, `list --chat nope` ("no checkpoints"), `get cp-1`, and `save --file -` from stdin. `ai-checkpoint resume forecasting-v2` output `==` MCP `resume_checkpoint` text over stdio: True. These errors are clean (rc 1, `error: …`, no traceback): unknown ref for resume and get, a missing file, invalid JSON, non-UTF-8 bytes, a directory, a missing field, wrong field types, and `[]`. **Not clean:** a JSON file whose top level is `"str"`, `null`, `5` or `[1]` prints a full Python traceback (`ValueError: dictionary update sequence element #0…` / `TypeError: 'NoneType' object is not iterable`) and exits 1. See "For the builder". |
| 10 | README: install and mcpServers registration | met | The README has an Install section (`pip install -e .[mcp]`) and an example `"mcpServers": {"ai-checkpoint": {"command": "ai-checkpoint-mcp", "env": {"AI_CHECKPOINT_HOME": …}}}`. It also covers the `python3 -m ai_checkpoint.server` alternative, `claude mcp add ai-checkpoint --env AI_CHECKPOINT_HOME=… -- ai-checkpoint-mcp`, CLI usage and the brief format. |

Test suite: `python3 -m pytest -q` gave 51 passed in 3.56s.

## Extra checks
These are notes only. None of them changes the verdict.
- **The `resume` prompt with an unknown ref** fails as a JSON-RPC error with only the generic text "Error rendering prompt resume". The server logs a full traceback chain to stderr, ending in `NotFoundError: checkpoint not found: 'nope'`. The server keeps running. A user who picks the prompt in Claude Desktop with a mistyped ref would not see why it failed. Criterion 4 only covers tools, so this is not a FAIL. It is worth returning a message that names the problem, or raising an error type the SDK passes through.
- **In-process tests** assert that `server.call_tool` raises `ToolError`. They do not assert `isError`. I checked the behaviour directly with the SDK's in-memory `mcp.Client(server)`, and it does return `is_error=True`. The test could use `Client(server)` so it checks the result the criterion names.
- `ai-checkpoint save --file arr.json` with `[]` reports "chat_name: is required". That is clean but misleading. The real problem is that the file is not an object.
- `AI_CHECKPOINT_HOME=/proc/nope ai-checkpoint list` prints "no checkpoints" with rc 0. It does not report the path as unusable.
- `pyproject.toml` declares `mcp>=1.2`, but the 1.x fallback (`mcp.server.fastmcp`) is untested, as the build log says. Pin `mcp>=2` or test on 1.x.
- `import ai_checkpoint` does not import `mcp`. The core stays dependency-free.
- Redaction (F-001) still runs before the brief is built. A verbatim item that contains something like `password=…` will not be reproduced byte for byte. That is intended F-001 behaviour, but users should know about it.
- What a new chat sees: the brief reads well. It names the checkpoint, says the reader has not seen the conversation, tells the model not to reopen settled decisions and to ask instead of guessing, and ends with the confirm-the-step instruction. Error text over MCP has the SDK prefix "Error executing tool X:", followed by a message that names the field.

## Regression sweep
Code paths touched: `src/ai_checkpoint/brief.py` (`render_brief` was rewritten; `fence_for`, `fenced` and helpers were added; `estimate_tokens` is unchanged). `pyproject.toml` (added `[project.scripts]`). New files: server.py, cli.py and __main__.py. store.py, model.py and redact.py are not modified. `GitStore.list` calls `render_brief`, so listings are the F-001 path the change touches.

Method: `git worktree add <scratch>/old HEAD` (F-001). I ran the same script against both `src` trees with a fixed clock and a fresh store each time. It did 10 saves: valid ones; ones with verbatim, decisions and a secret in context; resumed_from by `cp-1`; and invalid ones (empty next_steps, unknown resumed_from, `/` in chat_name, missing objective, a `cp-005` name, blank objective). Then `resolve` and `get` on 13 refs: `cp-1`, `cp-001`, `c/n`, `n`, `N`, `other/n`, `v2`, `cp-999`, `""`, `c/zz`, `C/V2`, `cp-0` and `cp-1000`. Then `list` for None, `c`, `other`, `zzz` and `""`.

Differences: the 622-line JSON outputs are identical except for the `brief_tokens` values (old 55/54/66/53 against new 265/281/284/263). That change is intended. The F-001 test suite from the HEAD worktree (`old/tests`, 38 tests) passes against the new `src`. I removed the worktree afterwards. `git worktree list` shows only the main tree.

## For the builder (FAIL only)
1. **CLI traceback on non-object JSON (criterion 9).** Reproduce:
   ```
   export AI_CHECKPOINT_HOME=$(mktemp -d)
   echo '"str"' | ai-checkpoint save --file -   # ValueError traceback, rc 1
   echo 'null'  | ai-checkpoint save --file -   # TypeError traceback
   echo '5'     | ai-checkpoint save --file -   # TypeError traceback
   echo '[1]'   | ai-checkpoint save --file -   # TypeError traceback
   ```
   The cause is that `GitStore.save` calls `dict(data)` on whatever it is given, and `cli._run` passes the parsed JSON straight through. Correct behaviour is one line on stderr, such as `error: <file> must contain a JSON object (got str)`, exit status non-zero and no traceback. A check in `cli.py` after `json.loads` is enough, though rejecting non-mappings in the store would also protect other callers. Add these cases to `tests/test_brief_cli.py::test_cli_errors_clean`. `[]` should get the same "must contain a JSON object" message instead of "chat_name: is required".

## Brief as a new chat reads it (cp-001, via MCP resume_checkpoint)
`````
You are continuing work from checkpoint cp-001 (sales-forecast/forecasting-v2), saved 2026-10-07T01:45:35Z in claude-code.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective
Build a weekly sales forecast for 40 stores to drive staffing.
## Context
Data in Snowflake table SALES.WEEKLY; user prefers Python/statsmodels; no Prophet.
## Decisions already made
- Use SARIMAX per store
  Reason: Prophet rejected: install issues on their cluster
## Completed so far
- Pulled 3 years of data
- Cleaned holiday weeks
## Current step
Tuning SARIMAX orders for store 12; got to (1,1,1)(0,1,1,52), MAPE 8.4%
## Next steps
1. Grid search store 12 remaining orders
2. Roll out to all 40 stores
3. Write staffing translation
## Open questions
- Is week 53 merged or dropped?
## Verbatim material
Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.
**model call**  (6-backtick fence; content omitted here)
**SQL**  (3-backtick fence)
## Last exchange
**User** (3-backtick fence)  **Assistant** (4-backtick fence)
## Notes from the previous AI
User dislikes long preambles.
## Before you continue
Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
`````
(Blank lines between the section headings and the fenced blocks are shortened here. The real output keeps them.)
