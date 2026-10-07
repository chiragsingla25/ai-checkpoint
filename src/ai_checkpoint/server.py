"""Local stdio MCP server for AI Checkpoint (requires the optional ``mcp`` extra).

Run with ``ai-checkpoint-mcp`` or ``python -m ai_checkpoint.server``. The store
is ``$AI_CHECKPOINT_HOME`` or ``~/.ai-checkpoint``.

The ``save_checkpoint`` tool description and its per-field descriptions are
the compaction instructions for the model that saves: every model that calls
the tool fills the same sections.
"""
from __future__ import annotations

from typing import Any, List, Optional

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from pydantic import BaseModel, Field

from .brief import estimate_tokens, render_brief
from .errors import CheckpointError
from .store import GitStore

SERVER_NAME = "ai-checkpoint"

SERVER_INSTRUCTIONS = (
    "AI Checkpoint saves named restore points of this chat and resumes them in a new chat. "
    "When the user asks to checkpoint, save or hand over this chat, call save_checkpoint. "
    "When the user asks to resume or continue from a checkpoint, call resume_checkpoint and "
    "follow the brief it returns."
)

SAVE_DESCRIPTION = """\
Save this chat as a named checkpoint so the user can resume it later in a brand-new chat \
(possibly in a different AI app). You are the compactor: you have the whole conversation \
in context, and the next chat will have ONLY what you write here, nothing else.

How to fill it in:
- Fill EVERY section, using the WHOLE conversation from its start, not just the last few \
messages. Do not leave a section empty if the conversation has anything for it.
- Put code, commands, numbers, formulas, file contents, prompts, names, URLs and any exact \
wording the work depends on into `verbatim`, character for character, each with a short \
label. Never summarise or paraphrase inside `verbatim`; copy it.
- Copy the last user message and your last reply into `last_exchange` word for word.
- Write for a reader who has seen none of this chat: spell out what "it", "the file" and \
"the previous approach" refer to, and record the reason behind each decision so settled \
questions are not reopened.
- Never invent anything. If something was not said or decided in the conversation, leave it \
out or list it under `open_questions`. Do not guess file contents, numbers or intentions.
- Do not include secrets (API keys, passwords, tokens); describe where they live instead.
- `current_step` is the exact step the chat was on at this moment, and `next_steps` are \
ordered, concrete instructions the next AI can follow without asking.

Pick a short, descriptive `checkpoint_name` (for example "forecasting-v2"). If this chat was \
itself resumed from a checkpoint, pass that checkpoint's id as `resumed_from` so the \
checkpoints form a branch tree. Returns the new checkpoint id and the git commit hash.\
"""


class DecisionIn(BaseModel):
    decision: str = Field(description="What was decided, stated plainly.")
    reason: str = Field(description="Why it was decided, including options that were rejected.")


class VerbatimIn(BaseModel):
    label: str = Field(description="Short label saying what this is, e.g. 'SQL query' or 'system prompt'.")
    content: str = Field(
        description="The exact text, copied character for character (code, numbers, wording, "
        "file contents). Never paraphrase or abbreviate."
    )


class LastExchangeIn(BaseModel):
    user: str = Field(default="", description="The last user message, word for word.")
    assistant: str = Field(
        default="", description="Your most recent reply, word for word (before this save)."
    )


def _wrap(fn):
    """Run ``fn`` and turn core errors into MCP tool errors naming the problem."""
    try:
        return fn()
    except CheckpointError as e:
        raise ToolError(str(e)) from e


def create_server(store: Optional[GitStore] = None):
    """Build the MCP server. ``store`` defaults to a GitStore on the default root."""
    mcp = _Server(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    def get_store() -> GitStore:
        return store if store is not None else GitStore()

    @mcp.tool(description=SAVE_DESCRIPTION)
    def save_checkpoint(
        chat_name: str = Field(description="Name of this chat/project (no '/'). Checkpoints of one chat are grouped under it."),
        checkpoint_name: str = Field(description="Short name for this restore point, e.g. 'forecasting-v2'."),
        objective: str = Field(description="What the work is for: the goal this whole chat is serving."),
        current_step: str = Field(description="The exact step the chat was on when saved: what was being done, and how far it got."),
        next_steps: List[str] = Field(description="Ordered, concrete instructions for continuing from the current step. At least one."),
        context: str = Field(default="", description="Background facts, constraints, environment and preferences the user stated that the next AI must respect."),
        decisions: List[DecisionIn] = Field(default_factory=list, description="Each decision made, with its reason, so settled questions are not reopened."),
        completed: List[str] = Field(default_factory=list, description="What is already done."),
        open_questions: List[str] = Field(default_factory=list, description="Unresolved questions or items still waiting on the user."),
        verbatim: List[VerbatimIn] = Field(default_factory=list, description="Material that must not be paraphrased: code, numbers, exact wording, file contents. Each with a label."),
        last_exchange: LastExchangeIn = Field(default_factory=LastExchangeIn, description="The last user message and the last assistant reply, word for word."),
        notes_for_next_ai: str = Field(default="", description="Anything else the next AI must know that fits no other section: pitfalls, user's style, things already tried."),
        client: Optional[str] = Field(default=None, description="The app this chat is in, e.g. 'claude.ai', 'chatgpt', 'claude-code'."),
        resumed_from: Optional[str] = Field(default=None, description="Id of the checkpoint this chat was resumed from (e.g. 'cp-007'), if any. Must exist."),
    ) -> dict[str, Any]:
        data = dict(
            chat_name=chat_name, checkpoint_name=checkpoint_name, objective=objective,
            current_step=current_step, next_steps=next_steps, context=context,
            decisions=[d.model_dump() for d in decisions], completed=completed,
            open_questions=open_questions, verbatim=[v.model_dump() for v in verbatim],
            last_exchange=last_exchange.model_dump(), notes_for_next_ai=notes_for_next_ai,
            client=client, resumed_from=resumed_from,
        )
        return _wrap(lambda: get_store().save(data).to_dict())

    @mcp.tool()
    def list_checkpoints(
        chat_name: Optional[str] = Field(default=None, description="Only list checkpoints of this chat."),
    ) -> dict[str, Any]:
        """List saved checkpoints, newest first, also grouped by chat. Each entry has its id,
        names, created_at, client, resumed_from and brief_tokens (estimated size of its resume
        brief, characters/4)."""
        return _wrap(lambda: get_store().list(chat_name).to_dict())

    @mcp.tool()
    def get_checkpoint(
        ref: str = Field(description="Checkpoint id (cp-007), checkpoint name, or chat_name/checkpoint_name."),
    ) -> dict[str, Any]:
        """Return the stored checkpoint as data, plus brief_chars and brief_tokens (estimated
        size of its resume brief, characters/4). Use resume_checkpoint to continue the work."""
        def run():
            cp = get_store().get(ref)
            brief = render_brief(cp)
            return {**cp.to_dict(), "brief_chars": len(brief), "brief_tokens": estimate_tokens(brief)}
        return _wrap(run)

    @mcp.tool()
    def resume_checkpoint(
        ref: str = Field(description="Checkpoint id (cp-007), checkpoint name, or chat_name/checkpoint_name."),
    ) -> str:
        """Return the continuation brief for a checkpoint. Read it and carry on from it: it
        names the checkpoint, gives the objective, decisions, current step and next steps,
        verbatim material and the last exchange, and tells you to confirm the current step
        with the user before continuing."""
        return _wrap(lambda: render_brief(get_store().get(ref)))

    @mcp.prompt(name="resume", description="Resume a saved checkpoint in this chat.")
    def resume(ref: str) -> str:
        return _wrap(lambda: render_brief(get_store().get(ref)))

    return mcp


def main() -> None:
    create_server().run("stdio")


if __name__ == "__main__":
    main()
