"""Local stdio MCP server for AI Checkpoint (requires the optional ``mcp`` extra).

Run with ``ai-checkpoint-mcp`` or ``python -m ai_checkpoint.server``. The store
is ``$AI_CHECKPOINT_HOME`` or ``~/.ai-checkpoint``.

The ``save_checkpoint`` tool description and its per-field descriptions are
the compaction instructions for the model that saves: every model that calls
the tool fills the same sections.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from pydantic import BaseModel, ConfigDict, Field

from .brief import estimate_tokens, render_brief
from . import structured as _structured
from .errors import CheckpointError
from .schema import FIELD_DESCRIPTIONS, SAVE_DESCRIPTION
from .store import GitStore

SERVER_NAME = "ai-checkpoint"

SERVER_INSTRUCTIONS = (
    "AI Checkpoint saves named restore points of a chat and resumes them in a new chat.\n"
    "- If the user asks to checkpoint, save or hand over this chat, call save_checkpoint.\n"
    "- If the user asks to resume or continue a checkpoint, including a bare ref like "
    "'resume trial/test-v1', call resume_checkpoint with that ref. Do not search files, git "
    "or the web for it.\n"
    "- Names: chat_name is a short name for the chat or project, with no '/'. checkpoint_name is "
    "a short descriptive name such as 'forecasting-v2'. If the user gives 'chat/checkpoint', "
    "split it into those two parts.\n"
    "- On resume, read the returned brief and confirm the current step with the user before "
    "continuing.\n"
    "- If the ref is unknown or ambiguous, call list_checkpoints."
)

FD = FIELD_DESCRIPTIONS


class RejectedIn(BaseModel):
    option: str = Field(description=FD["decisions.rejected.option"])
    how_far: Literal["discussed", "prototyped", "built_then_removed"] = Field(
        description=FD["decisions.rejected.how_far"]
    )
    note: Optional[str] = Field(default=None, description=FD["decisions.rejected.note"])


class DecisionIn(BaseModel):
    decision: str = Field(description=FD["decisions.decision"])
    reason: str = Field(description=FD["decisions.reason"])
    rejected: List[RejectedIn] = Field(default_factory=list, description=FD["decisions.rejected"])
    status: Literal["active", "superseded"] = Field(default="active", description=FD["decisions.status"])
    supersedes: Optional[str] = Field(default=None, description=FD["decisions.supersedes"])


class TaskIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    text: str = Field(description=FD["tasks.text"])
    status: Literal["todo", "in_progress", "done"] = Field(default="todo", description=FD["tasks.status"])
    from_: Literal["user", "ai"] = Field(default="ai", alias="from", description=FD["tasks.from"])
    quote: Optional[str] = Field(default=None, description=FD["tasks.quote"])
    depends_on: List[str] = Field(default_factory=list, description=FD["tasks.depends_on"])
    order: Optional[int] = Field(default=None, description=FD["tasks.order"])


class PlanUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[str] = Field(default=None, description=FD["plan_updates.id"])
    text: Optional[str] = Field(default=None, description=FD["plan_updates.text"])
    status: Optional[Literal["todo", "in_progress", "done"]] = Field(
        default=None, description=FD["tasks.status"])
    from_: Optional[Literal["user", "ai"]] = Field(
        default=None, alias="from", description=FD["tasks.from"])
    quote: Optional[str] = Field(default=None, description=FD["tasks.quote"])
    depends_on: Optional[List[str]] = Field(default=None, description=FD["plan_updates.depends_on"])
    order: Optional[int] = Field(default=None, description=FD["tasks.order"])


class FactIn(BaseModel):
    key: str = Field(description=FD["facts.key"])
    value: str = Field(description=FD["facts.value"])
    valid_from: Optional[str] = Field(default=None, description=FD["facts.valid_from"])
    superseded_by: Optional[str] = Field(default=None, description=FD["facts.superseded_by"])


class QuestionIn(BaseModel):
    text: str = Field(description=FD["open_questions.text"])
    waiting_on_user: bool = Field(default=False, description=FD["open_questions.waiting_on_user"])


Status = Literal["still_relevant", "done_with"]


class WsFile(BaseModel):
    path: str
    note: Optional[str] = None
    status: Status


class WsRepo(BaseModel):
    path: str
    branch: Optional[str] = None
    last_commit: Optional[str] = None
    note: Optional[str] = None
    status: Status


class WsAccess(BaseModel):
    path: str
    permissions: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    status: Status


class WsNamed(BaseModel):
    name: str
    note: Optional[str] = None
    status: Status


class WsEnvVar(BaseModel):
    name: str = Field(description="The variable NAME only, never its value.")
    status: Status


class WsReference(BaseModel):
    name: str
    url: Optional[str] = None
    note: Optional[str] = None
    status: Status


class WorkspaceIn(BaseModel):
    files: List[WsFile] = Field(default_factory=list, description=FD["workspace.files"])
    repos: List[WsRepo] = Field(default_factory=list, description=FD["workspace.repos"])
    access: List[WsAccess] = Field(default_factory=list, description=FD["workspace.access"])
    connectors: List[WsNamed] = Field(default_factory=list, description=FD["workspace.connectors"])
    tools: List[WsNamed] = Field(default_factory=list, description=FD["workspace.tools"])
    env_vars: List[WsEnvVar] = Field(default_factory=list, description=FD["workspace.env_vars"])
    skills: List[WsNamed] = Field(default_factory=list, description=FD["workspace.skills"])
    references: List[WsReference] = Field(default_factory=list, description=FD["workspace.references"])


class VerbatimIn(BaseModel):
    label: str = Field(description=FD["verbatim.label"])
    content: str = Field(description=FD["verbatim.content"])


class LastExchangeIn(BaseModel):
    user: str = Field(default="", description=FD["last_exchange.user"])
    assistant: str = Field(default="", description=FD["last_exchange.assistant"])


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
        chat_name: str = Field(description=FD["chat_name"]),
        checkpoint_name: str = Field(description=FD["checkpoint_name"]),
        objective: str = Field(description=FD["objective"]),
        current_step: str = Field(description=FD["current_step"]),
        next_steps: List[str] = Field(default_factory=list, description=FD["next_steps"]),
        tasks: Optional[List[TaskIn]] = Field(default=None, description=FD["tasks"]),
        plan_updates: Optional[List[PlanUpdateIn]] = Field(
            default=None, description=FD["plan_updates"]),
        user_turns: List[str] = Field(default_factory=list, description=FD["user_turns"]),
        facts: List[FactIn] = Field(default_factory=list, description=FD["facts"]),
        context: str = Field(default="", description=FD["context"]),
        decisions: List[DecisionIn] = Field(default_factory=list, description=FD["decisions"]),
        completed: List[str] = Field(default_factory=list, description=FD["completed"]),
        open_questions: Optional[List[Union[str, QuestionIn]]] = Field(
            default=None, description=FD["open_questions"]),
        verbatim: Optional[List[VerbatimIn]] = Field(default=None, description=FD["verbatim"]),
        last_exchange: LastExchangeIn = Field(default_factory=LastExchangeIn, description=FD["last_exchange"]),
        notes_for_next_ai: str = Field(default="", description=FD["notes_for_next_ai"]),
        workspace: Optional[WorkspaceIn] = Field(default=None, description=FD["workspace"]),
        client: Optional[str] = Field(default=None, description=FD["client"]),
        resumed_from: Optional[str] = Field(default=None, description=FD["resumed_from"]),
    ) -> dict[str, Any]:
        data = dict(
            chat_name=chat_name, checkpoint_name=checkpoint_name, objective=objective,
            current_step=current_step, next_steps=next_steps, context=context,
            decisions=[d.model_dump(exclude_none=True) for d in decisions], completed=completed,
            open_questions=(None if open_questions is None else
                            [q if isinstance(q, str) else q.model_dump() for q in open_questions]),
            verbatim=None if verbatim is None else [v.model_dump() for v in verbatim],
            last_exchange=last_exchange.model_dump(), notes_for_next_ai=notes_for_next_ai,
            workspace=workspace.model_dump() if workspace else None,
            client=client, resumed_from=resumed_from,
        )
        if tasks is not None:  # an explicit [] reaches the "no unfinished task" check
            data["tasks"] = [t.model_dump(by_alias=True, exclude_none=True) for t in tasks]
        if plan_updates is not None:
            data["plan_updates"] = [u.model_dump(by_alias=True, exclude_none=True)
                                    for u in plan_updates]
        if user_turns:
            data["user_turns"] = user_turns
        if facts:
            data["facts"] = [f.model_dump(exclude_none=True) for f in facts]
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
            return {**cp.to_dict(), **_structured.to_dict(cp), "brief_chars": len(brief), "brief_tokens": estimate_tokens(brief)}
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
