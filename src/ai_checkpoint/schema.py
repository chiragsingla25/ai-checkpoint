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
- For EVERY decision where alternatives were discussed, list each one in `rejected` with how \
far it got (discussed, prototyped, built_then_removed), even when the reason is short or the \
option was only mentioned. Leave `rejected` empty only if no alternative came up.
- Fill `workspace` with the environment the work used: folders and files, repos (branch and \
last commit), access that had to be granted, connectors or MCP servers, tools and setup, \
env var NAMES, skills/plugins/agents and external references. Judge each item: mark it \
`still_relevant` if the work will need it again, `done_with` if not. List `done_with` items \
too; do not leave them out. Examples: an abandoned folder (give its full path), an old file \
name after a rename, a connector or tool no longer used, an env var NAME that was used. Give \
env var names only, never their values, and no credential paths.
- `current_step` is the exact step the chat was on at this moment.
- `tasks` is the plan: one item per step, in order (the order to do them). Each has `text`, `status` \
(todo, in_progress or done), `from` and `quote`. Put steps the user asked for first, with \
`from` "user" and `quote` = the user's own words for that step, copied exactly from one of \
their messages. Never invent a quote. Put those messages in `user_turns` (the user's key \
messages, word for word). Steps you propose yourself have `from` "ai" and no quote. List \
finished steps too, as done. At least one task must be todo or in_progress. The server \
numbers them for you; in depends_on, task k of your list is t-k. It works out the next \
action itself.
- Old form: `next_steps` (strings, the user's own steps first, each starting with the exact \
text "User's plan:") still works, but prefer `tasks`.

Pick a short, descriptive `checkpoint_name` (for example "forecasting-v2").\
"""

#: Only meaningful for a tool call (ids and commits come from the store).
SAVE_TOOL_SUFFIX = (
    "If this chat was itself resumed from a checkpoint, pass that checkpoint's id as "
    "`resumed_from` so the checkpoints form a branch tree, and do not rewrite the plan: give "
    "`plan_updates` instead of `tasks` ({id, status} changes a task shown in the brief; an item "
    "without id is a new task). Returns the new checkpoint id "
    "and the git commit hash."
)

SAVE_DESCRIPTION = SAVE_INSTRUCTIONS + " " + SAVE_TOOL_SUFFIX

#: Field name (dotted for nested fields) -> description shown to the saving model.
FIELD_DESCRIPTIONS = {
    "chat_name": "Name of this chat/project (no '/'). Checkpoints of one chat are grouped under it.",
    "checkpoint_name": "Short name for this restore point, e.g. 'forecasting-v2'.",
    "objective": "What the work is for: the goal this whole chat is serving.",
    "current_step": "The exact step the chat was on when saved: what was being done, and how far it got.",
    "next_steps": (
        "Old form of the plan, as strings. Prefer `tasks`. If you use it: at least one step; the "
        "user's own steps first, in their words and in order, each starting with \"User's plan:\"; "
        "your own steps after."
    ),
    "tasks": (
        "The plan: ordered steps, the user's own steps first. Each {text, status, from, quote, "
        "depends_on?, order?}. Give this instead of next_steps. At least one task must be todo "
        "or in_progress. The server numbers them for you; in depends_on, task k of your list is t-k."
    ),
    "plan_updates": (
        "Only with resumed_from, instead of tasks. Changes to the parent checkpoint's plan: "
        "{id, status?, depends_on?, order?} edits the task with that id (the id is shown in the "
        "brief, e.g. t-2); an item without id is a new task {text, from, quote, status?}. "
        "Tasks you do not mention stay as they were."
    ),
    "plan_updates.depends_on": (
        "Optional. Ids of tasks that must be done first: the real task ids shown in the brief "
        "(e.g. [\"t-3\"]) or the ids of new tasks in this list, NOT list positions."
    ),
    "plan_updates.id": "Id of an existing task from the brief, e.g. \"t-2\". Leave out for a new task.",
    "plan_updates.text": "New tasks only: what to do. Existing tasks cannot be reworded.",
    "tasks.text": "What to do: one concrete step the next AI can follow without asking.",
    "tasks.status": "todo, in_progress or done. Steps already finished are listed too, as done.",
    "tasks.from": "\"user\" if the user asked for this step, \"ai\" if you propose it.",
    "tasks.quote": (
        "Required when from is \"user\": the user's exact words for this step, copied from one of "
        "their messages (also listed in user_turns). Leave out for ai tasks."
    ),
    "tasks.depends_on": "Optional. Numbers of tasks that must be done first, e.g. [\"t-1\"]. Task k in your list is t-k.",
    "tasks.order": "Optional. A number that sorts tasks, lowest first. Leave out to keep your list order.",
    "user_turns": (
        "The user's key messages, word for word: their goal, their plan, corrections and "
        "decisions. Every user quote in `tasks` must come from here or from last_exchange.user."
    ),
    "facts": (
        "Optional. Facts the next AI must treat as currently true, each {key, value, valid_from?}. "
        "A new fact with the same key replaces the old one."
    ),
    "facts.key": "What the fact is about, e.g. 'data frequency'.",
    "facts.value": "The current value, e.g. 'weekly'.",
    "facts.valid_from": "Optional. Since when it is true (a date or a few words).",
    "facts.superseded_by": "Optional. Number of a later fact in this list that replaces this one, e.g. \"f-2\".",
    "context": "Background facts, constraints, environment and preferences the user stated that the next AI must respect.",
    "decisions": (
        "Each decision made, with its reason, so settled questions are not reopened. "
        "For each decision, list in `rejected` the alternatives that were turned down."
    ),
    "decisions.decision": "What was decided, stated plainly.",
    "decisions.reason": "Why it was decided, including options that were rejected.",
    "decisions.rejected": (
        "`rejected` must hold every alternative discussed for this decision, even when the reason is "
        "short; empty only if none came up. Each as "
        "{option, how_far, note?}. `how_far` is how far it got: \"discussed\" (only talked about), "
        "\"prototyped\" (a trial or spike was made) or \"built_then_removed\" (fully built, then "
        "taken out). `note` is an optional short remark. This lets the next chat answer "
        "\"was X ever tried?\"."
    ),
    "decisions.status": "\"active\" (default) or \"superseded\".",
    "decisions.supersedes": (
        "Optional. Number of an earlier decision in this list that this one replaces, e.g. "
        "\"d-1\". Decision k in your list is d-k."
    ),
    "decisions.rejected.option": "The rejected alternative, named plainly.",
    "decisions.rejected.how_far": (
        "One of \"discussed\", \"prototyped\", \"built_then_removed\": how far the rejected "
        "option got before it was dropped."
    ),
    "decisions.rejected.note": "Optional. Why it was dropped or what the trial showed.",
    "completed": "What is already done.",
    "workspace": (
        "Optional. The environment the work depended on, as an object of lists: files, repos, "
        "access, connectors, tools, env_vars, skills, references. Every item has a `status` of "
        "\"still_relevant\" or \"done_with\"; judge each one. Only still-relevant items are "
        "shown to the next chat as a 'Set up first' checklist, but done-with items must be listed too, "
        "not dropped. Env var names only, never values."
    ),
    "workspace.files": "Files or folders worked with: {path, note?, status}. Key files to open first.",
    "workspace.repos": "Repos: {path, branch?, last_commit?, note?, status}. Branch and last commit at save time.",
    "workspace.access": (
        "Access that had to be granted: {path, permissions?: array of strings such as \"delete\" "
        "or \"push\", note?, status}. The path is the folder."
    ),
    "workspace.connectors": "Connectors or MCP servers used: {name, note?, status}.",
    "workspace.tools": "Tools and setup (venv or interpreter, CLIs, local servers or ports): {name, note?, status}.",
    "workspace.env_vars": "Environment variables needed, by NAME only: {name, status}. Never include a value.",
    "workspace.skills": "Skills, plugins or agents used: {name, note?, status}.",
    "workspace.references": "External references (URL, doc, ticket, artifact): {name, url?, note?, status}.",
    "open_questions": (
        "Unresolved questions. Each is a string, or {text, waiting_on_user}. Set waiting_on_user "
        "to true when you asked the user and are waiting for the answer."
    ),
    "open_questions.text": "The question.",
    "open_questions.waiting_on_user": "true if the user was asked and has not answered yet.",
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
    (
        "decisions",
        "array of {decision: string, reason: string, rejected?: array of "
        "{option: string, how_far: \"discussed\"|\"prototyped\"|\"built_then_removed\", note?: string}, "
        "status?: \"active\"|\"superseded\", supersedes?: string}",
        False,
    ),
    ("completed", "array of strings", False),
    ("current_step", "string", True),
    ("next_steps", "array of strings (old form; give tasks instead)", False),
    (
        "tasks",
        "array of {text: string, status?: \"todo\"|\"in_progress\"|\"done\", from?: \"user\"|\"ai\", "
        "quote?: string, depends_on?: array of strings, order?: integer}; required unless "
        "next_steps is given",
        False,
    ),
    ("user_turns", "array of strings", False),
    (
        "facts",
        "array of {key: string, value: string, valid_from?: string, superseded_by?: string}",
        False,
    ),
    ("open_questions", "array of strings or {text: string, waiting_on_user?: boolean}", False),
    ("verbatim", "array of {label: string, content: string}", False),
    ("last_exchange", "object {user: string, assistant: string}", False),
    ("notes_for_next_ai", "string", False),
    (
        "workspace",
        "object of arrays (files, repos, access, connectors, tools, env_vars, skills, "
        "references); each item has a status \"still_relevant\"|\"done_with\"",
        False,
    ),
    ("client", "string or null", False),
)

_NESTED = ("decisions", "verbatim", "last_exchange", "workspace", "tasks", "facts", "open_questions")


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
