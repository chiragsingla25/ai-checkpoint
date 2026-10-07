# AI Checkpoint

Named restore points for AI chats. Save a chat as a checkpoint from inside the
chat, then resume it in a brand-new chat and carry on from the exact step.
See `docs/IDEA.md` for the idea.

Checkpoints are JSON files in a local git repo (one commit per save). Store
location: `~/.ai-checkpoint`, or `$AI_CHECKPOINT_HOME`.

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
