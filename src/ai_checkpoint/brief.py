"""Resume-brief rendering hook.

F-001 only needs an approximate token count of the brief for listings. This
module is the integration point: ``render_brief`` is a plain placeholder
rendering that F-002 replaces with the real continuation brief (same
signature). ``GitStore.list`` calls ``render_brief`` + ``estimate_tokens``, so
listings pick up the real brief automatically.
"""
from __future__ import annotations

import math

from .model import Checkpoint


def estimate_tokens(text: str) -> int:
    """Approximate token count (chars / 4, rounded up). No tokenizer dependency."""
    return math.ceil(len(text) / 4)


def render_brief(cp: Checkpoint) -> str:
    """Placeholder brief: every section in fixed order. TODO(F-002): final wording."""
    d = cp.to_dict()
    lines = [
        f"You are continuing from checkpoint {cp.checkpoint_name} ({cp.checkpoint_id}) "
        f"of chat {cp.chat_name}.",
        f"Objective: {cp.objective}",
        f"Context: {cp.context}",
        "Decisions:",
        *[f"- {x['decision']} (because {x['reason']})" for x in d["decisions"]],
        "Completed:",
        *[f"- {x}" for x in cp.completed],
        f"Current step: {cp.current_step}",
        "Next steps:",
        *[f"{i}. {x}" for i, x in enumerate(cp.next_steps, 1)],
        "Open questions:",
        *[f"- {x}" for x in cp.open_questions],
        "Verbatim:",
        *[f"[{x['label']}]\n{x['content']}" for x in d["verbatim"]],
        f"Last user message: {cp.last_exchange.user}",
        f"Last assistant reply: {cp.last_exchange.assistant}",
        f"Notes: {cp.notes_for_next_ai}",
    ]
    return "\n".join(lines)
