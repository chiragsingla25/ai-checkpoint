"""Checkpoint bundle format v2 (see docs/DESIGN-v2.md). Stdlib only.

A bundle is a folder ``chats/<chat>/checkpoints/cp-NNN/`` of small files. This
module writes and reads that folder and knows how a chat name becomes a folder
name. It does not touch git; ``store.GitStore`` does that.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional

from .errors import ValidationError
from .model import Checkpoint

BUNDLE_VERSION = 2
USER_PLAN_PREFIX = "User's plan:"
_USER_PLAN_RE = re.compile(r"^User's plan:\s*")
_SLUG_BAD = re.compile(r"[^a-z0-9._-]+")
_LABEL_BAD = re.compile(r"[^a-z0-9]+")
BUNDLE_FILES = ("core.json", "plan.json", "decisions.jsonl", "facts.jsonl", "workspace.json",
                "user_turns.jsonl", "open_questions.json", "brief.md")


# ---------------------------------------------------------------- names
def chat_key(chat_name: str) -> str:
    """Normalised chat identity: NFKC, stripped, casefolded (DESIGN-v2 section 4)."""
    return unicodedata.normalize("NFKC", chat_name).strip().casefold()


def chat_folder(chat_name: str) -> str:
    """Base folder name ``<slug>-<hash8>`` for a chat (before any collision suffix)."""
    key = chat_key(chat_name)
    slug = _SLUG_BAD.sub("-", key)
    slug = re.sub(r"-{2,}", "-", slug).strip("-.")[:40].strip("-.") or "chat"
    return f"{slug}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]}"


def verbatim_filename(position: int, label: str) -> str:
    """``NN-<slug>.txt``; the position prefix keeps duplicate labels apart."""
    slug = _LABEL_BAD.sub("-", label.lower()).strip("-")[:40].strip("-") or "item"
    return f"{position:02d}-{slug}.txt"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------- plan
def tasks_from_next_steps(next_steps: List[str]) -> List[dict]:
    """Old ``next_steps`` -> tasks (DESIGN-v2 section 12)."""
    tasks = []
    for i, step in enumerate(next_steps, 1):
        m = _USER_PLAN_RE.match(step)
        text = step[m.end():] if m else step
        task = {"id": f"t-{i}", "text": text, "status": "todo",
                "from": "user" if m else "ai", "quote": text if m else None,
                "depends_on": [], "order": 10 * i}
        if m:
            task["raw"] = step  # original step text, so the flat view reads back byte for byte
        tasks.append(task)
    return tasks


def next_action(tasks: List[dict]) -> Optional[dict]:
    """First task by order that is todo and whose depends_on are all done, else None."""
    status = {t["id"]: t["status"] for t in tasks}

    def num(t):
        return int(t["id"].split("-")[1])

    for t in sorted(tasks, key=lambda t: (t["order"], num(t))):
        if t["status"] == "todo" and all(status.get(d) == "done" for d in t["depends_on"]):
            return {"task_id": t["id"], "text": t["text"]}
    return None


def next_steps_from_tasks(tasks: List[dict]) -> List[str]:
    """Inverse of ``tasks_from_next_steps`` (tasks in order)."""
    out = []
    for t in sorted(tasks, key=lambda t: (t["order"], int(t["id"].split("-")[1]))):
        if t["from"] == "user":
            out.append(t.get("raw") or f"{USER_PLAN_PREFIX} {t['text']}")
        else:
            out.append(t["text"])
    return out


# ------------------------------------------------------------- encoding
def dumps_json(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def dumps_jsonl(rows: List[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n"
                   for r in rows).encode("utf-8")


# ---------------------------------------------------------------- write
def bundle_files(cp: Checkpoint, brief_text: str) -> "dict[str, bytes]":
    """Every file of the bundle (relative path -> bytes), except manifest.json."""
    ce = cp.to_dict()
    tasks = tasks_from_next_steps(cp.next_steps)
    decisions = []
    for i, d in enumerate(ce["decisions"], 1):
        decisions.append({"id": f"d-{i}", "decision": d["decision"], "reason": d["reason"],
                          "rejected": d.get("rejected", []), "status": "active",
                          "supersedes": None})
    turns = ([{"n": 1, "text": cp.last_exchange.user}] if cp.last_exchange.user else [])
    files = {
        "core.json": dumps_json({
            "objective": cp.objective, "context": cp.context, "completed": list(cp.completed),
            "current_step": cp.current_step, "notes_for_next_ai": cp.notes_for_next_ai,
            "last_exchange": {"user": cp.last_exchange.user,
                              "assistant": cp.last_exchange.assistant}}),
        "plan.json": dumps_json({"version": BUNDLE_VERSION, "tasks": tasks,
                                 "next_action": next_action(tasks)}),
        "decisions.jsonl": dumps_jsonl(decisions),
        "facts.jsonl": b"",
        "workspace.json": dumps_json({c: [dict(i) for i in items]
                                      for c, items in cp.workspace.items()}),
        "user_turns.jsonl": dumps_jsonl(turns),
        "verbatim/.keep": b"",  # keeps verbatim/ in git clones when there are no items
        "open_questions.json": dumps_json({"questions": [
            {"id": f"q-{i}", "text": q, "waiting_on_user": False}
            for i, q in enumerate(cp.open_questions, 1)]}),
        "brief.md": brief_text.encode("utf-8"),
    }
    for i, v in enumerate(cp.verbatim, 1):
        files["verbatim/" + verbatim_filename(i, v.label)] = v.content.encode("utf-8")
    return files


def write_bundle(folder: Path, cp: Checkpoint, brief_text: str) -> None:
    """Create ``folder`` (must not exist) with all files and the manifest."""
    files = bundle_files(cp, brief_text)
    folder.mkdir(parents=True)
    (folder / "verbatim").mkdir()
    for rel, data in files.items():
        with open(folder / rel, "xb") as fh:  # binary: no newline translation
            fh.write(data)
    manifest = {
        "version": BUNDLE_VERSION, "id": cp.checkpoint_id, "chat_name": cp.chat_name,
        "checkpoint_name": cp.checkpoint_name, "resumed_from": cp.resumed_from,
        "created_at": cp.created_at, "client": cp.client,
        "files": {rel: sha256_bytes(data) for rel, data in files.items()},
        "verbatim": [{"label": v.label, "file": "verbatim/" + verbatim_filename(i, v.label)}
                     for i, v in enumerate(cp.verbatim, 1)],
    }
    with open(folder / "manifest.json", "xb") as fh:
        fh.write(dumps_json(manifest))


# ----------------------------------------------------------------- read
def read_bundle(folder: Path) -> Checkpoint:
    """Load a bundle as the flat ``Checkpoint`` view. Raises on any corruption."""
    def jload(name):
        return json.loads((folder / name).read_text(encoding="utf-8"))

    def jlines(name):
        text = (folder / name).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    man = jload("manifest.json")
    if not isinstance(man, dict) or man.get("version") != BUNDLE_VERSION:
        raise ValueError("unsupported bundle version")
    core, plan = jload("core.json"), jload("plan.json")
    decisions = [{k: v for k, v in d.items() if k in ("decision", "reason", "rejected") and
                  not (k == "rejected" and not v)}
                 for d in jlines("decisions.jsonl") if d.get("status", "active") == "active"]
    verbatim = [{"label": v["label"],
                 "content": (folder / v["file"]).read_bytes().decode("utf-8")}
                for v in man.get("verbatim", [])]
    questions = [q["text"] for q in jload("open_questions.json")["questions"]]
    data = {
        "checkpoint_id": man["id"], "chat_name": man["chat_name"],
        "checkpoint_name": man["checkpoint_name"], "created_at": man["created_at"],
        "client": man["client"], "resumed_from": man["resumed_from"],
        "objective": core["objective"], "context": core["context"],
        "decisions": decisions, "completed": core["completed"],
        "current_step": core["current_step"],
        "next_steps": next_steps_from_tasks(plan["tasks"]),
        "open_questions": questions, "verbatim": verbatim,
        "last_exchange": core["last_exchange"], "notes_for_next_ai": core["notes_for_next_ai"],
        "workspace": jload("workspace.json"),
    }
    try:
        return Checkpoint.from_dict(data)
    except ValidationError as e:
        raise ValueError(str(e)) from None
