"""Structured (v2) checkpoint data: plan tasks, decisions with status, facts, user turns,
open questions. Stdlib only. See docs/DESIGN-v2.md sections 5, 7 and 9.

``build`` validates the new save fields and returns a ``V2``; it never touches disk.
``Checkpoint.v2`` holds it; the flat ``Checkpoint`` fields stay the old-API view.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from . import bundle as _bundle
from .errors import CheckError, ValidationError
from .model import Checkpoint, _rejected_dict

TASK_STATUS = ("todo", "in_progress", "done")
TASK_FROM = ("user", "ai")
DECISION_STATUS = ("active", "superseded")
_TASK_ID_RE = re.compile(r"^t-(\d+)$")


@dataclass
class V2:
    tasks: List[dict] = field(default_factory=list)
    decisions: List[dict] = field(default_factory=list)
    facts: List[dict] = field(default_factory=list)
    user_turns: List[dict] = field(default_factory=list)
    questions: List[dict] = field(default_factory=list)
    manifest: Optional[dict] = None


def task_number(task_id: str) -> int:
    m = _TASK_ID_RE.match(task_id)
    return int(m.group(1)) if m else 0


def max_task_number(tasks: List[dict]) -> int:
    return max([task_number(t["id"]) for t in tasks] + [0])


def _err(field_: str, msg: str):
    return ValidationError(field_, msg)


def _list(v: Any, name: str) -> list:
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        raise _err(name, f"must be a list, got {type(v).__name__}")
    return list(v)


def _req(item: Mapping, key: str, at: str) -> str:
    v = item.get(key)
    if v is None:
        raise _err(f"{at}.{key}", "is required")
    if not isinstance(v, str):
        raise _err(f"{at}.{key}", f"must be a string, got {type(v).__name__}")
    if not v.strip():
        raise _err(f"{at}.{key}", "must not be empty")
    return v


def _opt(item: Mapping, key: str, at: str) -> Optional[str]:
    v = item.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise _err(f"{at}.{key}", f"must be a string, got {type(v).__name__}")
    return v if v.strip() else None


def _norm_key(s: str) -> str:
    return " ".join(s.split()).casefold()


# ------------------------------------------------------------------ tasks
def _parse_tasks(raw: list, base: int) -> List[dict]:
    ids = [f"t-{base + k}" for k in range(1, len(raw) + 1)]
    tasks = []
    for i, item in enumerate(raw):
        at = f"tasks[{i}]"
        if not isinstance(item, Mapping):
            raise _err(at, f"must be an object, got {type(item).__name__}")
        status = item.get("status") or "todo"
        if status not in TASK_STATUS:
            raise _err(f"{at}.status", f"must be one of {', '.join(TASK_STATUS)}, got {status!r}")
        frm = item.get("from") or "ai"
        if frm not in TASK_FROM:
            raise _err(f"{at}.from", f"must be one of {', '.join(TASK_FROM)}, got {frm!r}")
        deps = item.get("depends_on")
        if deps is None:
            deps = []
        if not isinstance(deps, (list, tuple)) or not all(isinstance(d, str) for d in deps):
            raise _err(f"{at}.depends_on", "must be a list of task ids such as [\"t-1\"]")
        order = item.get("order")
        if order is None:
            order = 10 * (i + 1)
        if isinstance(order, bool) or not isinstance(order, int):
            raise _err(f"{at}.order", f"must be an integer, got {type(order).__name__}")
        quote = _opt(item, "quote", at) if frm == "user" else None
        tasks.append({"id": ids[i], "text": _req(item, "text", at), "status": status,
                      "from": frm, "quote": quote, "depends_on": [d.strip() for d in deps],
                      "order": order})
    # depends_on is positional in a fresh list: "t-k" means the k-th item of THIS list.
    # Rewrite it to the id actually assigned (t-(base+k)); anything else is unknown.
    for i, t in enumerate(tasks):
        out = []
        for d in t["depends_on"]:
            m = re.fullmatch(r"t-(\d+)", d)
            k = int(m.group(1)) if m else 0
            if not 1 <= k <= len(ids):
                raise _err(f"tasks[{i}].depends_on", f"unknown task {d}")
            out.append(ids[k - 1])
        t["depends_on"] = out
    check_dependencies(tasks, "tasks")
    return tasks


def check_dependencies(tasks: List[dict], name: str) -> None:
    """Unknown dependency ids and cycles are validation errors."""
    known = {t["id"] for t in tasks}
    for i, t in enumerate(tasks):
        for d in t["depends_on"]:
            if d not in known:
                raise _err(f"{name}[{i}].depends_on", f"unknown task {d}")
    deps = {t["id"]: t["depends_on"] for t in tasks}
    state: Dict[str, int] = {}

    def visit(tid: str, path: List[str]):
        if state.get(tid) == 2:
            return
        if state.get(tid) == 1:
            cycle = path[path.index(tid):] + [tid]
            raise _err(name, "dependency cycle " + " -> ".join(cycle))
        state[tid] = 1
        for d in deps[tid]:
            visit(d, path + [tid])
        state[tid] = 2

    for t in tasks:
        visit(t["id"], [])


# ------------------------------------------------------------------ build
def build(data: Mapping, cp: Checkpoint, task_base: int = 0) -> V2:
    """Validate the structured fields of ``data`` (already redacted) against ``cp``."""
    raw_tasks = _list(data.get("tasks"), "tasks")
    if raw_tasks:
        tasks = _parse_tasks(raw_tasks, task_base)
    else:
        tasks = _bundle.tasks_from_next_steps(cp.next_steps)
        for t in tasks:
            t["id"] = f"t-{task_base + task_number(t['id'])}"
    v2 = V2(tasks=tasks)

    raw_dec = _list(data.get("decisions"), "decisions")
    for i, d in enumerate(cp.decisions):
        item = raw_dec[i] if i < len(raw_dec) and isinstance(raw_dec[i], Mapping) else {}
        at = f"decisions[{i}]"
        status = item.get("status") or "active"
        if status not in DECISION_STATUS:
            raise _err(f"{at}.status", f"must be one of {', '.join(DECISION_STATUS)}, got {status!r}")
        sup = _opt(item, "supersedes", at)
        v2.decisions.append({"id": f"d-{i + 1}", "decision": d.decision, "reason": d.reason,
                             "rejected": [_rejected_dict(r) for r in d.rejected],
                             "status": status, "supersedes": sup})
    ids = {d["id"]: n for n, d in enumerate(v2.decisions)}
    for i, d in enumerate(v2.decisions):
        sup = d["supersedes"]
        if sup is not None:
            if sup not in ids or ids[sup] >= i:
                raise _err(f"decisions[{i}].supersedes",
                           f"unknown decision {sup} (name an earlier decision in this list, "
                           "such as d-1)")
            v2.decisions[ids[sup]]["status"] = "superseded"

    raw_facts = _list(data.get("facts"), "facts")
    active: Dict[str, dict] = {}
    for i, item in enumerate(raw_facts):
        at = f"facts[{i}]"
        if not isinstance(item, Mapping):
            raise _err(at, f"must be an object, got {type(item).__name__}")
        fact = {"id": f"f-{i + 1}", "key": _req(item, "key", at), "value": _req(item, "value", at),
                "valid_from": _opt(item, "valid_from", at),
                "superseded_by": _opt(item, "superseded_by", at)}
        v2.facts.append(fact)
    fids = {f["id"] for f in v2.facts}
    for i, f in enumerate(v2.facts):
        if f["superseded_by"] is not None and f["superseded_by"] not in fids:
            raise _err(f"facts[{i}].superseded_by", f"unknown fact {f['superseded_by']}")
        k = _norm_key(f["key"])
        prev = active.get(k)
        if prev is not None and prev["superseded_by"] is None:
            prev["superseded_by"] = f["id"]
        active[k] = f

    raw_turns = _list(data.get("user_turns"), "user_turns")
    seen = set()
    for i, t in enumerate(raw_turns):
        if not isinstance(t, str):
            raise _err(f"user_turns[{i}]", f"must be a string, got {type(t).__name__}")
        if t.strip() and t not in seen:
            seen.add(t)
            v2.user_turns.append({"n": len(v2.user_turns) + 1, "text": t})
    if not raw_turns and cp.last_exchange.user.strip():
        v2.user_turns.append({"n": 1, "text": cp.last_exchange.user})

    raw_q = _list(data.get("open_questions"), "open_questions")
    for i, text in enumerate(cp.open_questions):
        item = raw_q[i] if i < len(raw_q) else None
        waiting = False
        if isinstance(item, Mapping):
            waiting = item.get("waiting_on_user", False)
            if waiting is None:
                waiting = False
            if not isinstance(waiting, bool):
                raise _err(f"open_questions[{i}].waiting_on_user", "must be true or false")
        v2.questions.append({"id": f"q-{i + 1}", "text": text, "waiting_on_user": waiting})
    return v2


# ------------------------------------------------------------ save-time checks
def norm_text(s: str) -> str:
    """NFKC, casefold, punctuation/control/format -> space, collapse whitespace (DESIGN §8)."""
    out = []
    for ch in unicodedata.normalize("NFKC", s).casefold():
        out.append(" " if unicodedata.category(ch)[0] in "PC" else ch)
    return " ".join("".join(out).split())


def run_checks(data: Mapping, cp: Checkpoint, v2: V2) -> None:
    """Raise one CheckError listing every failing check (DESIGN §8). Input is already redacted.

    Checks 1 and 2 (user-task quotes) apply only when the save gives ``tasks`` (new tasks);
    tasks derived from old ``next_steps`` are never quote-checked. Check 3 applies to every save.
    """
    problems: List[str] = []
    raw_tasks = _list(data.get("tasks"), "tasks")
    if raw_tasks:
        pool = [" " + norm_text(t["text"]) + " " for t in v2.user_turns]
        if cp.last_exchange.user.strip():
            pool.append(" " + norm_text(cp.last_exchange.user) + " ")
        for k, t in enumerate(v2.tasks, 1):
            if t["from"] != "user":
                continue
            quote = t.get("quote")
            if not quote:
                problems.append(f"Task t-{k} is from=user but has no quote. Give the user's exact "
                                'words as quote, or set from to "ai".')
                continue
            nq = norm_text(quote)
            if not nq or not any(" " + nq + " " in turn for turn in pool):
                problems.append(
                    f"Task t-{k} is from=user but its quote was not found in user_turns or "
                    f'last_exchange.user: "{quote}". Copy the user\'s exact words from the '
                    "conversation into user_turns (or last_exchange.user) and use the same words "
                    'as the quote, or set from to "ai".')
    if all(t["status"] == "done" for t in v2.tasks):
        problems.append("The plan has no unfinished task (every task is done, or there are no "
                        "tasks). Add at least one task with status todo or in_progress for what "
                        "happens next.")
    if problems:
        raise CheckError(problems)


def from_flat(cp: Checkpoint) -> V2:
    """Structured view of an old-style checkpoint (nothing but the flat fields)."""
    return build({}, cp)


def finalize(v2: V2, created_at: str) -> None:
    for f in v2.facts:
        if not f["valid_from"]:
            f["valid_from"] = created_at


# ------------------------------------------------------------ next action
def next_action_info(tasks: List[dict]) -> dict:
    """The computed next action plus what the brief needs when there is none."""
    action = _bundle.next_action(tasks)
    status = {t["id"]: t["status"] for t in tasks}
    unfinished = [t for t in tasks if t["status"] != "done"]
    in_progress = [t for t in unfinished if t["status"] == "in_progress"]
    blocked = []
    for t in sorted(tasks, key=lambda t: (t["order"], task_number(t["id"]))):
        if t["status"] == "todo":
            unmet = [d for d in t["depends_on"] if status.get(d) != "done"]
            if unmet:
                blocked.append((t, unmet))
    task = next((t for t in tasks if action and t["id"] == action["task_id"]), None)
    return {"action": action, "task": task, "in_progress": in_progress, "blocked": blocked,
            "all_done": not unfinished}


def echo_text(info: dict) -> str:
    """The save-result line: ``Next action saved: <task text>. Correct?``"""
    if info["action"]:
        return f"Next action saved: {info['action']['text']}. Correct?"
    why = "every task is done" if info["all_done"] else "no task is ready"
    return f"Next action saved: none ({why}). Correct?"


def to_dict(cp: Checkpoint) -> dict:
    """The structured fields of a bundle checkpoint, for ``get_checkpoint`` (empty for old files)."""
    v2 = cp.v2
    if v2 is None:
        return {}
    info = next_action_info(v2.tasks)
    return {
        "tasks": v2.tasks,
        "plan": {"version": 2, "tasks": v2.tasks, "next_action": info["action"]},
        "next_action": info["action"],
        "decisions_v2": v2.decisions,
        "facts": v2.facts,
        "user_turns": v2.user_turns,
        "open_questions_v2": v2.questions,
        "manifest": v2.manifest,
    }
