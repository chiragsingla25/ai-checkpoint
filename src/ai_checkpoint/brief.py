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

from .model import Checkpoint


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


def render_brief(cp: Checkpoint) -> str:
    """Render the continuation brief for ``cp``."""
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
    parts.append(
        "## Before you continue\n\n"
        "Start by telling the user, in one or two sentences, which step you understand "
        "the work to be at (the current step above) and what you plan to do next. "
        "Ask them to confirm or correct that before you carry on. Then continue from "
        "the current step."
    )
    return "\n\n".join(parts) + "\n"
