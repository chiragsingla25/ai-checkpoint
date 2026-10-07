# AI Checkpoint

Named restore points for AI chats. See `docs/IDEA.md` for the idea.

This package currently contains the checkpoint format, validation, secret
redaction and the git-backed local store (`ai_checkpoint`). The MCP server, CLI
and evaluation kit build on it.

```
pip install -e .[dev]
pytest
```

Store location: `~/.ai-checkpoint`, or `$AI_CHECKPOINT_HOME`.
