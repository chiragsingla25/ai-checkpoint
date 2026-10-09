"""The resume brief: the text a brand-new chat receives to continue from a checkpoint.

``render_brief`` is deterministic (same checkpoint -> identical text) and is
written for a model to read. Sections always appear in ``BRIEF_ORDER``; an
empty optional section is shown as ``EMPTY_MARK`` so the layout never changes.
Verbatim items and the last exchange are placed in fenced code blocks whose
fence is longer than any backtick run inside, with the content reproduced
byte for byte (the fence line, one newline, the content, one newline, the
fence), so a reader or a test can extract it exactly.

``estimate_tokens`` is the documented size heuristic: ceil(characters / 4).
"""
from __future__ import annotations

import math
import re

from .model import WORKSPACE_CATEGORIES, Checkpoint


def estimate_tokens(text: str) -> int:
    """Approximate token count (chars / 4, rounded up). No tokenizer dependency."""
    return math.ceil(len(text) / 4)


#: Order of the sections in the brief (documented, fixed).
BRIEF_ORDER = (
    "Objective",
    "Context",
    "Decisions already made",
    "Completed so far",
    "Current step",
    "Next steps",
    "Open questions",
    "Verbatim material",
    "Last exchange",
    "Notes from the previous AI",
)

EMPTY_MARK = "_(none recorded)_"


def fence_for(text: str) -> str:
    """A backtick fence longer than any backtick run in ``text`` (minimum 3)."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def fenced(text: str) -> str:
    """``text`` in a fenced block; the content is reproduced byte for byte."""
    f = fence_for(text)
    return f"{f}\n{text}\n{f}"


def _text(value: str) -> str:
    return value if value.strip() else EMPTY_MARK


def _bullets(items) -> str:
    return "\n".join(f"- {x}" for x in items) if items else EMPTY_MARK


_HOW_FAR_WORDS = {
    "discussed": "discussed",
    "prototyped": "prototyped",
    "built_then_removed": "built, then removed",
}


def _decision(d) -> str:
    lines = [f"- {d.decision}", f"  Reason: {d.reason}"]
    for r in d.rejected:
        line = f"  Rejected: {_label(r.option)} ({_HOW_FAR_WORDS.get(r.how_far, r.how_far)})"
        if r.note.strip():
            line += f" - {_label(r.note)}"
        lines.append(line)
    return "\n".join(lines)


def _label(label: str) -> str:
    return " ".join(label.split())


def _item(it: dict, key: str, extras=()) -> str:
    line = _label(it[key])
    bits = [f"{lab} {_label(it[f])}" for f, lab in extras if it.get(f)]
    if it.get("permissions"):
        bits.append("permissions: " + ", ".join(_label(x) for x in it["permissions"]))
    if bits:
        line += " (" + "; ".join(bits) + ")"
    if it.get("note"):
        line += f" - {_label(it['note'])}"
    return line


def _setup_first(ws: dict) -> str:
    """The 'Set up first' checklist from still-relevant items; "" when there are none."""
    live = {c: [i for i in items if i.get("status") == "still_relevant"] for c, items in ws.items()}
    rows = []

    def add(title: str, cat: str, key: str, extras=()) -> None:
        if live.get(cat):
            rows.append(f"- {title}: " + "; ".join(_item(i, key, extras) for i in live[cat]))

    add("Folders to ask the user for access to", "access", "path")
    add("Connectors to check", "connectors", "name")
    add("Repos", "repos", "path", (("branch", "branch"), ("last_commit", "last commit")))
    add("Tools and setup", "tools", "name")
    add("Environment variables that must be set (names only)", "env_vars", "name")
    add("Skills, plugins and agents", "skills", "name")
    add("Files to open", "files", "path")
    add("References", "references", "name", (("url", "link"),))
    if not rows:
        return ""
    return (
        "## Set up first\n\n"
        "Ask the user before you request any folder access or connector; do not assume "
        "you already have it. Then check these:\n\n" + "\n".join(rows)
    )


def render_brief(cp: Checkpoint) -> str:
    """Render the continuation brief for ``cp``.

    Bundle checkpoints (``cp.v2`` set) get the v2 layout, old flat files the original one,
    which stays byte-identical.
    """
    if getattr(cp, "v2", None) is not None:
        return _render_v2(cp)
    return _render_flat(cp)


def _render_flat(cp: Checkpoint) -> str:
    ref = f"{cp.chat_name}/{cp.checkpoint_name}"
    head = [
        f"You are continuing work from checkpoint {cp.checkpoint_id} "
        f"({ref}), saved {cp.created_at or 'at an unknown time'} "
        f"in {cp.client or 'unknown'}.",
        "",
        "An earlier conversation was saved as this checkpoint so that you can pick the "
        "work up exactly where it stopped. You have not seen that conversation; this "
        "brief is everything you know about it. Treat it as accurate and do not reopen "
        "settled decisions unless the user asks. Where something is not in the brief, "
        "say so and ask instead of guessing.",
    ]
    if cp.resumed_from:
        head += ["", f"This checkpoint was itself saved from a chat resumed from {cp.resumed_from}."]

    parts = ["\n".join(head)]

    def section(title: str, body: str) -> None:
        parts.append(f"## {title}\n\n{body}")

    section("Objective", _text(cp.objective))
    section("Context", _text(cp.context))
    section(
        "Decisions already made",
        "\n".join(_decision(d) for d in cp.decisions) or EMPTY_MARK,
    )
    section("Completed so far", _bullets(cp.completed))
    section("Current step", _text(cp.current_step))
    section("Next steps", "\n".join(f"{i}. {x}" for i, x in enumerate(cp.next_steps, 1)) or EMPTY_MARK)
    section("Open questions", _bullets(cp.open_questions))
    if cp.verbatim:
        section(
            "Verbatim material",
            "Reproduced exactly as saved. Do not paraphrase, reformat or \"fix\" it.\n\n"
            + "\n\n".join(f"**{_label(v.label)}**\n{fenced(v.content)}" for v in cp.verbatim),
        )
    else:
        section("Verbatim material", EMPTY_MARK)
    ex = cp.last_exchange
    if ex.user.strip() or ex.assistant.strip():
        section(
            "Last exchange",
            "The final messages before the checkpoint was saved, word for word.\n\n"
            f"**User**\n{fenced(ex.user) if ex.user.strip() else EMPTY_MARK}\n\n"
            f"**Assistant**\n{fenced(ex.assistant) if ex.assistant.strip() else EMPTY_MARK}",
        )
    else:
        section("Last exchange", EMPTY_MARK)
    section("Notes from the previous AI", _text(cp.notes_for_next_ai))
    setup = _setup_first(cp.workspace)
    if setup:
        parts.append(setup)
    parts.append(
        "## Before you continue\n\n"
        "Start by telling the user, in one or two sentences, which step you understand "
        "the work to be at (the current step above) and what you plan to do next. "
        "Ask them to confirm or correct that before you carry on. Then continue from "
        "the current step."
    )
    return "\n\n".join(parts) + "\n"


# ------------------------------------------------------------------ v2 brief
def _task_line(t: dict) -> str:
    line = f"- [{t['id']}] ({t['status']}) {_label(t['text'])}"
    if t.get("depends_on"):
        line += " (after " + ", ".join(t["depends_on"]) + ")"
    if t.get("quote"):
        line += f' \u2014 user said: "{_label(t["quote"])}"'
    return line


def _next_action_section(info: dict) -> str:
    if info["action"]:
        t = info["task"]
        text = f"**[{t['id']}]** {_label(t['text'])}"
        if t.get("quote"):
            text += f'\nThe user said: "{_label(t["quote"])}"'
        return text
    if info["all_done"]:
        return "No unfinished tasks. Ask the user what to do next."
    parts = ["No task is ready."]
    if info["in_progress"]:
        parts.append("In progress: " + ", ".join(
            f'{t["id"]} "{_label(t["text"])}"' for t in info["in_progress"]) + ".")
    if info["blocked"]:
        parts.append("Blocked: " + ", ".join(
            f"{t['id']} (waiting on {', '.join(u)})" for t, u in info["blocked"]) + ".")
    return " ".join(parts)


def _no_longer_needed(ws: dict) -> str:
    rows = []
    for cat, (key, _o, _l) in WORKSPACE_CATEGORIES.items():
        for it in ws.get(cat, []):
            if it.get("status") == "done_with":
                rows.append(f"- {_item(it, key)} [{cat}]")
    if not rows:
        return ""
    return ("## No longer needed\n\nThe work is finished with these. Do not set them up or "
            "rely on them:\n\n" + "\n".join(rows))


def _render_v2(cp: Checkpoint) -> str:
    from . import structured
    v2 = cp.v2
    ref = f"{cp.chat_name}/{cp.checkpoint_name}"
    head = [
        f"You are continuing work from checkpoint {cp.checkpoint_id} "
        f"({ref}), saved {cp.created_at or 'at an unknown time'} "
        f"in {cp.client or 'unknown'}.",
        "",
        "An earlier conversation was saved as this checkpoint so that you can pick the "
        "work up exactly where it stopped. You have not seen that conversation; this "
        "brief is everything you know about it. Treat it as accurate and do not reopen "
        "settled decisions unless the user asks. Where something is not in the brief, "
        "say so and ask instead of guessing.",
    ]
    if cp.resumed_from:
        head += ["", f"This checkpoint was itself saved from a chat resumed from {cp.resumed_from}."]
    parts = ["\n".join(head)]

    def section(title: str, body: str) -> None:
        parts.append(f"## {title}\n\n{body}")

    def ordered(tasks):
        return sorted(tasks, key=lambda t: (t["order"], structured.task_number(t["id"])))

    info = structured.next_action_info(v2.tasks)
    section("Next action", _next_action_section(info))
    mine = [t for t in ordered(v2.tasks) if t["from"] == "user"]
    if mine:
        section("The user's plan", "These are the steps the user asked for, in their own words "
                "where quoted. Task numbers in [brackets] are used to update the plan.\n\n"
                + "\n".join(_task_line(t) for t in mine))
    ours = [t for t in ordered(v2.tasks) if t["from"] != "user"]
    if ours:
        section("Other planned work", "\n".join(_task_line(t) for t in ours))
    waiting = [q for q in v2.questions if q.get("waiting_on_user")]
    if waiting:
        section("Waiting on you (the user)", _bullets([q["text"] for q in waiting]))
    section("Objective", _text(cp.objective))
    section("Context", _text(cp.context))
    section("Decisions already made",
            "\n".join(_decision(d) for d in cp.decisions) or EMPTY_MARK)
    old = [d for d in v2.decisions if d["status"] == "superseded"]
    if old:
        parts[-1] += "\n\n### Superseded decisions\n\n" + "\n".join(
            f"- {_label(d['decision'])}" + (f" (replaced by {n['id']})" if (n := next(
                (x for x in v2.decisions if x["supersedes"] == d["id"]), None)) else "")
            for d in old)
    facts = [f for f in v2.facts if f.get("superseded_by") is None]
    if facts:
        section("Facts", "\n".join(
            f"- {_label(f['key'])}: {_label(f['value'])}"
            + (f" (since {_label(f['valid_from'])})" if f.get("valid_from") else "")
            for f in facts))
    section("Completed so far", _bullets(cp.completed))
    cur = _text(cp.current_step)
    busy = [t for t in ordered(v2.tasks) if t["status"] == "in_progress"]
    if busy:
        cur += "\n\nIn progress: " + "; ".join(f"[{t['id']}] {_label(t['text'])}" for t in busy)
    section("Current step", cur)
    section("Open questions", _bullets([q["text"] for q in v2.questions
                                        if not q.get("waiting_on_user")]))
    if cp.verbatim:
        section(
            "Verbatim material",
            "Reproduced exactly as saved. Do not paraphrase, reformat or \"fix\" it.\n\n"
            + "\n\n".join(f"**{_label(v.label)}**\n{fenced(v.content)}" for v in cp.verbatim),
        )
    else:
        section("Verbatim material", EMPTY_MARK)
    ex = cp.last_exchange
    if ex.user.strip() or ex.assistant.strip():
        section(
            "Last exchange",
            "The final messages before the checkpoint was saved, word for word.\n\n"
            f"**User**\n{fenced(ex.user) if ex.user.strip() else EMPTY_MARK}\n\n"
            f"**Assistant**\n{fenced(ex.assistant) if ex.assistant.strip() else EMPTY_MARK}",
        )
    else:
        section("Last exchange", EMPTY_MARK)
    setup = _setup_first(cp.workspace)
    if setup:
        parts.append(setup)
    gone = _no_longer_needed(cp.workspace)
    if gone:
        parts.append(gone)
    section("Notes from the previous AI", _text(cp.notes_for_next_ai))
    parts.append(
        "## Before you continue\n\n"
        "Start by telling the user, in one or two sentences, which step you understand "
        "the work to be at (the current step above) and that you plan to do the next "
        "action above. Ask them to confirm or correct that before you carry on. Then "
        "continue from the current step."
    )
    return "\n\n".join(parts) + "\n"
