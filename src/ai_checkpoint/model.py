"""Checkpoint data model and validation. Stdlib only.

``Checkpoint.from_dict`` is the single validation entry point. Errors are
``ValidationError`` with ``.field`` naming the offending field, e.g.
``next_steps``, ``verbatim[0].label``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .errors import ValidationError

ID_RE = re.compile(r"^cp-(\d+)$", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Section names in the fixed order used for storage and (later) briefs.
SECTION_FIELDS = (
    "objective",
    "context",
    "decisions",
    "completed",
    "current_step",
    "next_steps",
    "open_questions",
    "verbatim",
    "last_exchange",
    "notes_for_next_ai",
    "workspace",
)
METADATA_FIELDS = (
    "chat_name",
    "checkpoint_name",
    "checkpoint_id",
    "created_at",
    "client",
    "resumed_from",
)
#: Keys a caller supplies when saving (ids/timestamps are assigned by the store).
INPUT_FIELDS = tuple(
    f for f in METADATA_FIELDS + SECTION_FIELDS if f not in ("checkpoint_id", "created_at")
)


def format_id(n: int) -> str:
    return f"cp-{n:03d}"


def id_number(checkpoint_id: str) -> int:
    m = ID_RE.match(checkpoint_id)
    if not m:
        raise ValueError(f"not a checkpoint id: {checkpoint_id!r}")
    return int(m.group(1))


#: How far a rejected alternative got, from least to most effort spent on it.
HOW_FAR_VALUES = ("discussed", "prototyped", "built_then_removed")


@dataclass
class Rejected:
    option: str
    how_far: str
    note: str = ""


#: Whether a workspace item is still needed by the work.
STATUS_VALUES = ("still_relevant", "done_with")

#: Workspace categories: name -> (required key field, optional string fields,
#: optional string-list fields). Every item also carries a required ``status``.
WORKSPACE_CATEGORIES = {
    "files": ("path", ("note",), ()),
    "repos": ("path", ("branch", "last_commit", "note"), ()),
    "access": ("path", ("note",), ("permissions",)),
    "connectors": ("name", ("note",), ()),
    "tools": ("name", ("note",), ()),
    "env_vars": ("name", (), ()),
    "skills": ("name", ("note",), ()),
    "references": ("name", ("url", "note"), ()),
}


def empty_workspace() -> dict:
    return {cat: [] for cat in WORKSPACE_CATEGORIES}


@dataclass
class Decision:
    decision: str
    reason: str
    rejected: list = field(default_factory=list)


@dataclass
class VerbatimItem:
    label: str
    content: str


@dataclass
class LastExchange:
    user: str = ""
    assistant: str = ""


@dataclass
class Checkpoint:
    chat_name: str
    checkpoint_name: str
    objective: str
    current_step: str
    next_steps: list = field(default_factory=list)
    context: str = ""
    decisions: list = field(default_factory=list)
    completed: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    verbatim: list = field(default_factory=list)
    last_exchange: LastExchange = field(default_factory=LastExchange)
    notes_for_next_ai: str = ""
    workspace: dict = field(default_factory=empty_workspace)
    client: str = "unknown"
    resumed_from: Optional[str] = None
    checkpoint_id: str = ""
    created_at: str = ""
    #: Structured v2 data (structured.V2) for bundle checkpoints; None for old flat files.
    v2: Any = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ io
    def to_dict(self) -> dict:
        """JSON-ready dict containing every key (metadata first, then sections)."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "chat_name": self.chat_name,
            "checkpoint_name": self.checkpoint_name,
            "created_at": self.created_at,
            "client": self.client,
            "resumed_from": self.resumed_from,
            "objective": self.objective,
            "context": self.context,
            "decisions": [_decision_dict(d) for d in self.decisions],
            "completed": list(self.completed),
            "current_step": self.current_step,
            "next_steps": list(self.next_steps),
            "open_questions": list(self.open_questions),
            "verbatim": [{"label": v.label, "content": v.content} for v in self.verbatim],
            "last_exchange": {
                "user": self.last_exchange.user,
                "assistant": self.last_exchange.assistant,
            },
            "notes_for_next_ai": self.notes_for_next_ai,
            **self._workspace_part(),
        }

    def _workspace_part(self) -> dict:
        # omitted when empty so checkpoints without it keep their old shape
        ws = {cat: [dict(i) for i in items] for cat, items in self.workspace.items() if items}
        return {"workspace": ws} if ws else {}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Checkpoint":
        """Validate ``data`` and build a Checkpoint. Unknown keys are ignored.

        ``None`` for an optional field means "use the default".
        """
        if not isinstance(data, Mapping):
            raise ValidationError("checkpoint", "must be an object")
        g = data.get
        return cls(
            chat_name=_name(g("chat_name"), "chat_name", allow_slash=False),
            checkpoint_name=_name(g("checkpoint_name"), "checkpoint_name", allow_slash=True),
            objective=_req_str(g("objective"), "objective"),
            current_step=_req_str(g("current_step"), "current_step"),
            next_steps=_next_steps(g("next_steps"), g("tasks"), g("plan_updates")),
            context=_opt_str(g("context"), "context"),
            decisions=_decisions(g("decisions")),
            completed=_str_list(g("completed"), "completed"),
            open_questions=_questions(g("open_questions")),
            verbatim=_verbatim(g("verbatim")),
            last_exchange=_last_exchange(g("last_exchange")),
            notes_for_next_ai=_opt_str(g("notes_for_next_ai"), "notes_for_next_ai"),
            workspace=_workspace(g("workspace")),
            client=_opt_str(g("client"), "client") or "unknown",
            resumed_from=_opt_ref(g("resumed_from")),
            checkpoint_id=_opt_str(g("checkpoint_id"), "checkpoint_id"),
            created_at=_opt_str(g("created_at"), "created_at"),
        )


def _next_steps(v: Any, tasks: Any, plan_updates: Any = None) -> list:
    """``next_steps`` as given, or (when absent) the texts of ``tasks`` in the old step form."""
    if (v is None or (isinstance(v, (list, tuple)) and not v)) and isinstance(tasks, (list, tuple)) and tasks:
        steps = []
        for i, t in enumerate(tasks):
            if not isinstance(t, Mapping):
                raise ValidationError(f"tasks[{i}]", f"must be an object, got {_type_name(t)}")
            text = _req_str(t.get("text"), f"tasks[{i}].text")
            steps.append(f"User's plan: {text}" if t.get("from") == "user" else text)
        return steps
    if (v is None or (isinstance(v, (list, tuple)) and not v)) and plan_updates is not None \
            and tasks is None:
        return []  # the plan comes from the parent plus plan_updates (store.save)
    if (v is None or (isinstance(v, (list, tuple)) and not v)) and isinstance(tasks, (list, tuple)):
        # an explicitly empty plan (`tasks: []`): the "no unfinished task" check (DESIGN section 8)
        from .errors import CheckError
        raise CheckError(["The plan has no unfinished task (every task is done, or there are no "
                          "tasks). Add at least one task with status todo or in_progress for "
                          "what happens next."])
    if v is None or (isinstance(v, (list, tuple)) and not v):
        raise ValidationError("next_steps", "is required: give `tasks` (preferred) or `next_steps`")
    return _str_list(v, "next_steps", required=True)


def _questions(v: Any) -> list:
    """Open questions as texts; each item is a string or an object with ``text``."""
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        raise ValidationError("open_questions", f"must be a list, got {_type_name(v)}")
    return _str_list([i.get("text") if isinstance(i, Mapping) else i for i in v], "open_questions")


def _decision_dict(d: "Decision") -> dict:
    out = {"decision": d.decision, "reason": d.reason}
    if d.rejected:  # omitted when empty so checkpoints without it keep their old shape
        out["rejected"] = [_rejected_dict(r) for r in d.rejected]
    return out


def _rejected_dict(r: "Rejected") -> dict:
    out = {"option": r.option, "how_far": r.how_far}
    if r.note:
        out["note"] = r.note
    return out


# ------------------------------------------------------------- validators
def _type_name(v: Any) -> str:
    return "null" if v is None else type(v).__name__


def _req_str(v: Any, name: str) -> str:
    if v is None:
        raise ValidationError(name, "is required")
    if not isinstance(v, str):
        raise ValidationError(name, f"must be a string, got {_type_name(v)}")
    if not v.strip():
        raise ValidationError(name, "must not be empty")
    return v


def _opt_str(v: Any, name: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise ValidationError(name, f"must be a string, got {_type_name(v)}")
    return v


def _name(v: Any, name: str, *, allow_slash: bool) -> str:
    s = _req_str(v, name).strip()
    if _CONTROL_RE.search(s):
        raise ValidationError(name, "must not contain control characters or newlines")
    if not allow_slash and "/" in s:
        raise ValidationError(name, "must not contain '/'")
    if ID_RE.match(s):
        raise ValidationError(name, "must not look like a checkpoint id (cp-NNN)")
    return s


def _opt_ref(v: Any) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValidationError("resumed_from", f"must be a string, got {_type_name(v)}")
    return v.strip() or None


def _str_list(v: Any, name: str, *, required: bool = False) -> list:
    if v is None:
        if required:
            raise ValidationError(name, "is required")
        return []
    if not isinstance(v, (list, tuple)):
        raise ValidationError(name, f"must be a list of strings, got {_type_name(v)}")
    if required and not v:
        raise ValidationError(name, "must not be empty")
    out = []
    for i, item in enumerate(v):
        if not isinstance(item, str):
            raise ValidationError(f"{name}[{i}]", f"must be a string, got {_type_name(item)}")
        if not item.strip():
            raise ValidationError(f"{name}[{i}]", "must not be empty")
        out.append(item)
    return out


def _obj_list(v: Any, name: str) -> list:
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        raise ValidationError(name, f"must be a list of objects, got {_type_name(v)}")
    for i, item in enumerate(v):
        if not isinstance(item, Mapping):
            raise ValidationError(f"{name}[{i}]", f"must be an object, got {_type_name(item)}")
    return list(v)


def _decisions(v: Any) -> list:
    out = []
    for i, item in enumerate(_obj_list(v, "decisions")):
        out.append(
            Decision(
                decision=_req_str(item.get("decision"), f"decisions[{i}].decision"),
                reason=_req_str(item.get("reason"), f"decisions[{i}].reason"),
                rejected=_rejected(item.get("rejected"), f"decisions[{i}].rejected"),
            )
        )
    return out


def _rejected(v: Any, name: str) -> list:
    out = []
    for i, item in enumerate(_obj_list(v, name)):
        how_far = item.get("how_far")
        if how_far is None:
            raise ValidationError(f"{name}[{i}].how_far", "is required")
        if how_far not in HOW_FAR_VALUES:  # also rejects non-strings (unhashable-safe: tuple membership)
            raise ValidationError(
                f"{name}[{i}].how_far", f"must be one of {', '.join(HOW_FAR_VALUES)}, got {how_far!r}"
            )
        out.append(
            Rejected(
                option=_req_str(item.get("option"), f"{name}[{i}].option"),
                how_far=how_far,
                note=_opt_str(item.get("note"), f"{name}[{i}].note"),
            )
        )
    return out


def _workspace(v: Any) -> dict:
    out = empty_workspace()
    if v is None:
        return out
    if not isinstance(v, Mapping):
        raise ValidationError("workspace", f"must be an object, got {_type_name(v)}")
    for cat, (key, opt_strs, opt_lists) in WORKSPACE_CATEGORIES.items():
        base = f"workspace.{cat}"
        for i, item in enumerate(_obj_list(v.get(cat), base)):
            at = f"{base}[{i}]"
            entry = {key: _req_str(item.get(key), f"{at}.{key}")}
            if cat == "env_vars":
                # names only: "NAME=value" is reduced to "NAME", the value is never kept
                name = entry["name"].split("=", 1)[0].strip()
                if not name:
                    raise ValidationError(f"{at}.name", "must not be empty")
                entry["name"] = name
            for f in opt_strs:
                val = _opt_str(item.get(f), f"{at}.{f}")
                if val.strip():
                    entry[f] = val
            for f in opt_lists:
                vals = _str_list(item.get(f), f"{at}.{f}")
                if vals:
                    entry[f] = vals
            status = item.get("status")
            if status is None:
                raise ValidationError(f"{at}.status", "is required")
            if status not in STATUS_VALUES:
                raise ValidationError(
                    f"{at}.status", f"must be one of {', '.join(STATUS_VALUES)}, got {status!r}"
                )
            entry["status"] = status
            out[cat].append(entry)
    return out


def _verbatim(v: Any) -> list:
    out = []
    for i, item in enumerate(_obj_list(v, "verbatim")):
        out.append(
            VerbatimItem(
                label=_req_str(item.get("label"), f"verbatim[{i}].label"),
                content=_req_str(item.get("content"), f"verbatim[{i}].content"),
            )
        )
    return out


def _last_exchange(v: Any) -> LastExchange:
    if v is None:
        return LastExchange()
    if not isinstance(v, Mapping):
        raise ValidationError("last_exchange", f"must be an object, got {_type_name(v)}")
    return LastExchange(
        user=_opt_str(v.get("user"), "last_exchange.user"),
        assistant=_opt_str(v.get("assistant"), "last_exchange.assistant"),
    )
