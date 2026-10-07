# AI Checkpoint

Named restore points for AI chats. Save a chat as a checkpoint from inside the
chat, then resume it in a brand-new chat and carry on from the exact step.
See `docs/IDEA.md` for the idea.

Checkpoints are JSON files in a local git repo (one commit per save). Store
location: `~/.ai-checkpoint`, or `$AI_CHECKPOINT_HOME`.

## Quick start (macOS)

```
./scripts/setup-mac.sh --dry-run    # preview what it will do, changes nothing
./scripts/setup-mac.sh
```

Needs Python 3.10+ (`python3` on PATH, or `PYTHON=/path/to/python3`). The script
creates `.venv` in this repo, installs `.[mcp]`, registers `ai-checkpoint` with
Claude Code at user scope (if the `claude` CLI is installed) and adds it to the
Claude Desktop config (the old file is backed up next to it first). Safe to
re-run. Use `--desktop-config PATH` to edit a different config file. Then restart
Claude Desktop, run `/mcp` in Claude Code, and try "checkpoint this chat as
trial/test-v1" followed by "resume trial/test-v1" in a new chat.

## Install

```
pip install -e .[mcp]        # the MCP server needs the official `mcp` SDK
pip install -e .[mcp,dev]    # plus pytest
pytest
```

The core package and the CLI need no third-party dependencies.

## MCP server (Claude Desktop, Claude Code, any local MCP client)

Tools: `save_checkpoint`, `list_checkpoints`, `get_checkpoint`,
`resume_checkpoint`; prompt: `resume` (argument `ref`). A `ref` is a checkpoint
id (`cp-007`), a checkpoint name, or `chat_name/checkpoint_name`.

Claude Desktop (`claude_desktop_config.json`) or a project `.mcp.json`:

```json
{
  "mcpServers": {
    "ai-checkpoint": {
      "command": "ai-checkpoint-mcp",
      "env": { "AI_CHECKPOINT_HOME": "/Users/you/.ai-checkpoint" }
    }
  }
}
```

If the command is not on the client's PATH, use the full path to the script or
`"command": "python3", "args": ["-m", "ai_checkpoint.server"]` (with the
interpreter you installed into).

Claude Code:

```
claude mcp add ai-checkpoint --env AI_CHECKPOINT_HOME=$HOME/.ai-checkpoint -- ai-checkpoint-mcp
```

Then say "checkpoint this chat as forecasting-v2" in one chat, and
"resume forecasting-v2" in a new one.

## Windows notes

The store locks with `fcntl.flock` on macOS/Linux and `msvcrt.locking` on Windows, writes checkpoints as UTF-8 with `\n` line endings, ignores the user's `core.autocrlf` setting, and forces UTF-8 on CLI output. These behaviours are checked by `tests/test_windows_sim.py`, which only *simulates* Windows on Linux (hidden `fcntl`, fake `msvcrt`, CRLF files, autocrlf git config, cp1252 console). Real-Windows verification is done by the testers.

## CLI

```
ai-checkpoint save --file checkpoint.json
ai-checkpoint list [--chat NAME]
ai-checkpoint get REF        # stored checkpoint as JSON, with brief size estimate
ai-checkpoint resume REF     # prints the resume brief, same as the MCP tool
```

`python -m ai_checkpoint` is equivalent. Errors go to stderr with exit code 1.

## The resume brief

Deterministic text, in this order: header naming the checkpoint, Objective,
Context, Decisions already made, Completed so far, Current step, Next steps,
Open questions, Verbatim material, Last exchange, Notes from the previous AI,
and a closing instruction to confirm the current step with the user. Verbatim
items and the last exchange are in fenced blocks (fence longer than any
backtick run inside) and reproduced byte for byte. Empty sections show
`_(none recorded)_`. Size estimate (`brief_tokens`): characters / 4, rounded up.

## Handover evaluation kit

`checkpoint-eval` (or `python -m ai_checkpoint.eval`) measures how well a new
chat can continue the work from three kinds of handover, built from the same
conversation:

- `checkpoint`: a model call fills the checkpoint schema (the compaction prompt is
  generated from the same text as the `save_checkpoint` tool, `ai_checkpoint/schema.py`),
  the result is validated and rendered as the resume brief. If the output fails
  validation the variant is recorded as `failed` with the error.
- `summary`: a plain free-form summary from one model call.
- `full_history`: the raw conversation.

Each probe question is then asked in a fresh call that sees only the handover text
and the question; a judge call scores the answer.

Offline (deterministic fake model, no network, no API keys):

```
checkpoint-eval run examples/scenarios/invoice-sync.json --model fake --out out/
checkpoint-eval run examples/scenarios/delivery-restructure.json --model fake --out out2/
```

Two offline runs of the same scenario give identical files. Fake scores only prove
the pipeline works; they say nothing about real models.

With real models (the SDKs are optional extras, imported only when selected):

```
pip install -e .[anthropic]            # or .[openai]
export ANTHROPIC_API_KEY=...           # or OPENAI_API_KEY
checkpoint-eval run examples/scenarios/invoice-sync.json --model anthropic --out out/
checkpoint-eval run examples/scenarios/invoice-sync.json --model openai --model-name <model-id> --out out/
```

Default model ids are `claude-sonnet-5-5` (anthropic) and `gpt-5` (openai). Override with
`--model-name`, or the env vars `CHECKPOINT_EVAL_ANTHROPIC_MODEL` /
`CHECKPOINT_EVAL_OPENAI_MODEL` (the flag wins). The same model compacts, summarises,
answers and judges. A missing key or SDK prints a message naming it and exits 1.
Real runs make many calls (1 compaction + 1 summary + 3 x probes answers + 3 x probes
judgements, about 45 for the shipped scenarios).

Output in `--out`: `results.json` (per variant and probe: answer, per-fact judgement,
recall, contradictions; per-variant aggregates), `results.md` (the table, also printed),
and `handover_<variant>.md` (the exact handover text each variant used).

Metrics (per variant, averaged or summed over probes):

- **key-fact recall**: fraction of a probe's `key_facts` that the answer states, judged
  per fact; the table shows the mean over probes. Higher is better. Exact values (numbers,
  code, names) must match.
- **contradictions**: number of statements in answers that contradict the reference, the
  key facts or `must_not_contradict`, or assert something from `known_wrong` (for example a
  rejected option presented as chosen). Summed over probes. Lower is better; omissions do
  not count.
- **brief tokens**: estimated size of the handover (characters / 4). The cost side: the
  full history is the ceiling, a good checkpoint should recall nearly as much in far fewer.

A variant that failed (bad compaction output) shows `n/a`. If the judge reply is unusable
for a probe, that probe is excluded from the averages (see `probes_scored`).

### Scenario file format

```json
{
  "name": "optional-short-name",
  "description": "optional",
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "probes": [
    {
      "question": "asked in a fresh chat with only the handover",
      "key_facts": ["facts a correct answer contains"],
      "reference": "optional reference answer (default: key facts joined)",
      "must_not_contradict": ["optional true statements"],
      "known_wrong": ["optional plausible wrong claims"]
    }
  ]
}
```

`messages` must be non-empty with `role` of `user` or `assistant`; `probes` must be non-empty and
every probe needs a `question` and at least one `key_facts` entry. A malformed file gives an error
naming the field (for example `probes[2].key_facts: must not be empty`) and exit code 1. The fake
judge matches key facts by wording and `known_wrong` by substring; real judges read meaning.
