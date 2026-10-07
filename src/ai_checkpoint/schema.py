"""Single source of truth for the checkpoint save instructions.

Stdlib only. The MCP ``save_checkpoint`` tool (server.py) takes its description
and per-field descriptions from here, and the evaluation kit builds the
compaction prompt for real models from the same text, so the two never drift.
"""
from __future__ import annotations

SAVE_INSTRUCTIONS = """\
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

Pick a short, descriptive `checkpoint_name` (for example "forecasting-v2").\
"""

#: Only meaningful for a tool call (ids and commits come from the store).
SAVE_TOOL_SUFFIX = (
    "If this chat was itself resumed from a checkpoint, pass that checkpoint's id as "
    "`resumed_from` so the checkpoints form a branch tree. Returns the new checkpoint id "
    "and the git commit hash."
)

SAVE_DESCRIPTION = SAVE_INSTRUCTIONS + " " + SAVE_TOOL_SUFFIX

#: Field name (dotted for nested fields) -> description shown to the saving model.
FIELD_DESCRIPTIONS = {
    "chat_name": "Name of this chat/project (no '/'). Checkpoints of one chat are grouped under it.",
    "checkpoint_name": "Short name for this restore point, e.g. 'forecasting-v2'.",
    "objective": "What the work is for: the goal this whole chat is serving.",
    "current_step": "The exact step the chat was on when saved: what was being done, and how far it got.",
    "next_steps": "Ordered, concrete instructions for continuing from the current step. At least one.",
    "context": "Background facts, constraints, environment and preferences the user stated that the next AI must respect.",
    "decisions": "Each decision made, with its reason, so settled questions are not reopened.",
    "decisions.decision": "What was decided, stated plainly.",
    "decisions.reason": "Why it was decided, including options that were rejected.",
    "completed": "What is already done.",
    "open_questions": "Unresolved questions or items still waiting on the user.",
    "verbatim": "Material that must not be paraphrased: code, numbers, exact wording, file contents. Each with a label.",
    "verbatim.label": "Short label saying what this is, e.g. 'SQL query' or 'system prompt'.",
    "verbatim.content": (
        "The exact text, copied character for character (code, numbers, wording, "
        "file contents). Never paraphrase or abbreviate."
    ),
    "last_exchange": "The last user message and the last assistant reply, word for word.",
    "last_exchange.user": "The last user message, word for word.",
    "last_exchange.assistant": "Your most recent reply, word for word (before this save).",
    "notes_for_next_ai": "Anything else the next AI must know that fits no other section: pitfalls, user's style, things already tried.",
    "client": "The app this chat is in, e.g. 'claude.ai', 'chatgpt', 'claude-code'.",
    "resumed_from": "Id of the checkpoint this chat was resumed from (e.g. 'cp-007'), if any. Must exist.",
}

#: (field, JSON type, required) in the order they are presented to a model.
COMPACTION_FIELDS = (
    ("chat_name", "string", True),
    ("checkpoint_name", "string", True),
    ("objective", "string", True),
    ("context", "string", False),
    ("decisions", "array of {decision: string, reason: string}", False),
    ("completed", "array of strings", False),
    ("current_step", "string", True),
    ("next_steps", "array of strings (at least one)", True),
    ("open_questions", "array of strings", False),
    ("verbatim", "array of {label: string, content: string}", False),
    ("last_exchange", "object {user: string, assistant: string}", False),
    ("notes_for_next_ai", "string", False),
    ("client", "string or null", False),
)

_NESTED = ("decisions", "verbatim", "last_exchange")


def compaction_system_prompt() -> str:
    """System prompt for a model that must save a checkpoint without MCP tools.

    Built from the same instructions and field descriptions as the
    ``save_checkpoint`` tool; only the delivery changes (a JSON object in the
    reply instead of a tool call).
    """
    lines = [
        "TASK: COMPACT",
        "",
        SAVE_INSTRUCTIONS,
        "",
        "You cannot call tools here. Instead, reply with ONE JSON object (no prose, no code "
        "fence) holding the arguments of the save_checkpoint tool. Set `resumed_from` to null "
        "or omit it. Fields:",
    ]
    for name, typ, required in COMPACTION_FIELDS:
        lines.append(f"- `{name}` ({typ}; {'required' if required else 'optional'}): {FIELD_DESCRIPTIONS[name]}")
        if name in _NESTED:
            for key, text in FIELD_DESCRIPTIONS.items():
                if key.startswith(name + "."):
                    lines.append(f"    - `{key.split('.', 1)[1]}`: {text}")
    return "\n".join(lines)
