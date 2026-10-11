# Design v2: checkpoint bundles

Status: design for branch `feature/checkpoint-bundle-v2`. Features F-002..F-006 follow this document exactly; if a feature needs to deviate, change this document first.

## 1. Goal and constraints

Today a checkpoint is one file (`checkpoints/cp-NNN.json`) rendered into a brief. In the baseline eval (`eval-runs/2026-10-09-handover-v2-haiku`, handover-v2, 6 scenarios, 66 probes) the checkpoint handover scored **next step 50%** and **key-fact recall 88%**. The failure is mostly that the next AI cannot tell what to do first: `next_steps` is free text, the user's own plan is a string prefix convention, and nothing checks that the saved plan is faithful to what the user said.

v2 turns the checkpoint into a folder bundle of small structured files, computes the next action in code, checks the save before accepting it, and carries the plan forward by task id across resumes.

Constraints (unchanged): everything runs inside the one MCP server; no model, no API key, no network; Python stdlib only (plus the MCP/pydantic already used by `server.py`); one git commit per save; checkpoint ids global and sequential.

Targets (measured by a manual real-model eval, section 14): **next step >= 90%** (baseline 50%) and **key-fact recall >= 88%** (baseline 88%, must not drop). Push the branch only if both hold.

## 2. Prior art (why the design looks like this)

- **Anthropic long-running agent harness** ("Effective harnesses for long-running agents"): the harness keeps a JSON task list with a pass/fail status per item, and agents may only flip the status, not rewrite or delete items, because a model editing free text drifts. We use `plan.json` with typed tasks and status-only updates by id (section 11).
- **Claude Code compaction**: the compacted context keeps the user's own messages and rewrites the assistant side. We keep `user_turns.jsonl` and per-task `quote` verbatim for the same reason: the user's words are the ground truth for intent.
- **Zep / Graphiti temporal knowledge graph**: a changed fact does not overwrite the old one; the old fact is marked superseded with validity times. `facts.jsonl` and `decisions.jsonl` use `superseded_by` / `supersedes` so the brief shows only what is current while history stays readable.
- **Architecture Decision Records (ADRs)**: a decision records context, the choice, rejected options and a status (accepted, superseded by). `decisions.jsonl` is an ADR log in miniature.
- **Event sourcing**: state is derived from an append-only log. `chats/<chat>/events.jsonl` is append-only. We do not rebuild state from events (the bundle files are the state); the log is the audit trail and is what a later index would be built from.

## 3. Bundle layout

Root is `~/.ai-checkpoint` (overridable, as today). Old layout: `<root>/checkpoints/cp-NNN.json`. New layout:

```
~/.ai-checkpoint/
  checkpoints/cp-001.json            old flat files: read in place, never rewritten or moved
  chats/
    <chat>/                          folder name derived from chat_name (section 4)
      chat.json                      exact chat_name and its normalised key
      events.jsonl                   append-only, one line per save
      checkpoints/
        cp-004/                      one bundle per save
          manifest.json            identity, parent, client, sha256 of every other file
          core.json                objective, context, completed, current_step, notes_for_next_ai, last_exchange
          plan.json                tasks (the plan) and the derived next action
          decisions.jsonl          one decision per line
          facts.jsonl              one fact per line
          workspace.json           environment items with status
          user_turns.jsonl         the user's key messages verbatim
          verbatim/                exact snippets, one real file each
            01-model.txt
            .keep                    empty marker so verbatim/ exists in git clones; hashed in the manifest like any file
          open_questions.json      incl. waiting_on_user
          brief.md                 rendered view, never the source of truth
```

`core.json` is the only file beyond the list in the request. The old model has scalar sections (objective, context, completed, current step, notes, last exchange) that need a home; putting them in `core.json` keeps every other file single-purpose.

Everything is UTF-8 with `\n` line endings, JSON written with `ensure_ascii=False`, `indent=2`, keys in the order shown in the examples, one trailing newline. JSONL files have one compact JSON object per line (`separators=(",", ":")`). Deterministic output means the same input gives the same bytes and hashes.

Git: one commit per save containing exactly the new `cp-NNN/` folder, the chat's `events.jsonl` and (first save of a chat only) the chat's `chat.json`. Commit message as today: `checkpoint: cp-NNN <chat_name>/<checkpoint_name>` (after redaction). If the commit fails, the new folder is removed and `events.jsonl` is restored to its previous bytes. On a chat's **first** save there are no prior bytes: the newly created files and folders (`cp-NNN/`, `events.jsonl`, `chat.json`, and the chat folder itself if this save created it) are removed, leaving the store as before.

### Why a bundle and not a bigger JSON file

Small typed files let code operate on them: status updates touch `plan.json` only, `git diff` between two checkpoints shows what changed in the plan or the decisions, and verbatim material lives as real files (exact bytes, openable with any tool) instead of JSON-escaped strings.

## 4. Chat folder name and ids

**`<chat>` folder name.** Computed from `chat_name` by `chat_folder(chat_name)`:

1. Unicode-normalise with NFKC, strip surrounding whitespace, then `casefold()`. Call this the *key*. Two chat names with the same key are the same chat (this matches today's case-insensitive grouping and renumbering).
2. Build the slug from the key: keep `a-z`, `0-9`, `.`, `_`, `-`; replace every other character (spaces, `/`, punctuation, non-ASCII letters) with `-`; collapse runs of `-`; strip leading/trailing `-` and `.`; cut to 40 characters; if empty use `chat`.
3. The folder name is **always** `<slug>-<hash8>`, where `hash8` is the first 8 hex characters of `sha256(key.encode("utf-8"))`.
4. Each chat folder holds `chat.json` (section 5.10) with the exact `chat_name` and the `key`. Before using a folder name, the store checks it: if the folder exists and its `chat.json` has a different `key` (a hash collision, or a hand-made folder), append `-2` (then `-3`, ...) to the folder name until a folder is free or its `chat.json` has the same key. The hash makes collisions unlikely; the `chat.json` check makes them harmless.
5. Windows-reserved names are not special-cased (macOS and Linux are the targets).

Examples (real values): `forecast` -> `forecast-59f0db47`; `Forecast` -> the same folder (same key); `My Chat` -> `my-chat-674b8505`; `my-chat` -> `my-chat-b7af8317` (a different chat from `My Chat`, different folder); `預測` -> `chat-715fd30f`. `a/b` is not valid as a chat_name anyway (the existing validator rejects `/`).

The original `chat_name` is stored verbatim in `manifest.json` and in `chat.json` and is what listings display. The folder name is never parsed back; lookups find a chat by scanning `chats/*/chat.json` for its `key`, so a numeric suffix is transparent.

**Checkpoint ids.** `cp-NNN` is global and sequential across all chats, old flat files and bundles. The next id is `max(N)` + 1 over every id seen in: old flat files `checkpoints/cp-N.json`, bundle folders `chats/*/checkpoints/cp-N/`, **and git history** (today's `git log` scan of committed paths, extended to also match `chats/*/checkpoints/cp-N/`), so an id that was ever committed is never reused even if its files were later deleted by hand. It is assigned while holding the store lock (as today). It is zero-padded to three digits, and grows to four when needed (`cp-1000`). A save that is rejected by checks or whose commit fails leaves no folder and no commit, so its number is not in any of the three sources and is simply used by the next successful save.

**Refs** (`resolve`) behave as today: an id, a `checkpoint_name`, or `chat_name/checkpoint_name`, matched exactly first, then case-insensitively; renumbering (`name (1)`) is per chat key, across old and new checkpoints of that chat.

**Different chat_name on resume (owner ruling 4).** A save with `resumed_from=cp-X` under a different `chat_name` goes into the folder for the new name. `manifest.parent` and `resumed_from` link it to the parent, which may live in another chat folder or be an old flat file.

## 5. File schemas

Examples are one consistent checkpoint, `cp-004` in chat `forecast`, name `forecast-v2`, resumed from `cp-003`.

### 5.1 manifest.json

```json
{
  "version": 2,
  "id": "cp-004",
  "chat_name": "forecast",
  "checkpoint_name": "forecast-v2",
  "resumed_from": "cp-003",
  "created_at": "2026-10-09T09:41:05+00:00",
  "client": "claude-code",
  "files": {
    "core.json": "<sha256 hex>",
    "plan.json": "<sha256 hex>",
    "decisions.jsonl": "<sha256 hex>",
    "facts.jsonl": "<sha256 hex>",
    "workspace.json": "<sha256 hex>",
    "user_turns.jsonl": "<sha256 hex>",
    "open_questions.json": "<sha256 hex>",
    "brief.md": "<sha256 hex>",
    "verbatim/01-model.txt": "<sha256 hex>"
  },
  "verbatim": [
    {"label": "model", "file": "verbatim/01-model.txt"}
  ]
}
```

- `files` has a sha256 of every other file in the bundle (every file under `verbatim/` included), keyed by path relative to the bundle folder. `manifest.json` does not hash itself.
- `resumed_from` is the parent checkpoint id or `null`. (`parent` in the request wording is this field; there is no second field.)
- `verbatim` maps each label to its file, in saved order.
- `version: 2` identifies the bundle format. A reader that sees a higher version skips the bundle in listings rather than guessing.

### 5.2 core.json

```json
{
  "objective": "Finish the demand forecast",
  "context": "Weekly data, 3 years",
  "completed": ["Loaded data", "Cleaned outliers"],
  "current_step": "Tuning changepoints",
  "notes_for_next_ai": "User prefers terse answers",
  "last_exchange": {"user": "go on", "assistant": "ok"}
}
```

Same meaning and validation as the old fields of the same names.

### 5.3 plan.json

```json
{
  "version": 2,
  "tasks": [
    {"id": "t-1", "text": "Run the backtest on the last 52 weeks", "status": "done",
     "from": "user", "quote": "first run a backtest on the last year",
     "depends_on": [], "order": 10},
    {"id": "t-2", "text": "Write the report", "status": "todo",
     "from": "user", "quote": "then write the report for Dana",
     "depends_on": ["t-1"], "order": 20},
    {"id": "t-3", "text": "Tune holiday effects", "status": "todo",
     "from": "ai", "quote": null,
     "depends_on": [], "order": 30}
  ],
  "next_action": {"task_id": "t-2", "text": "Write the report"}
}
```

- `id`: `t-N`, assigned by the server, unique within the plan, never reused within a lineage, including when `tasks` replaces the plan (sections 7 and 11).
- `status`: `todo` | `in_progress` | `done`.
- `from`: `user` (the user said to do this) | `ai` (the AI proposes it). The brief lists user tasks first.
- `quote`: for `from=user`, the user's exact words that justify the task (required, checked in section 8); `null` for `ai`.
- `depends_on`: ids of tasks that must be `done` first (may be empty).
- `order`: integer, lower first. Ties are broken by task number.
- `next_action` is **derived** (section 9). It is written for readers of the file and ignored on load; the brief is rendered from the recomputed value.

### 5.4 decisions.jsonl

```json
{"id":"d-1","decision":"Use Prophet","reason":"handles seasonality","rejected":[{"option":"ARIMA","how_far":"discussed","note":"too slow"}],"status":"active","supersedes":null}
{"id":"d-2","decision":"Use weekly data only","reason":"hourly adds noise","rejected":[],"status":"active","supersedes":null}
{"id":"d-3","decision":"Use Prophet with logistic growth","reason":"capacity cap found","rejected":[],"status":"active","supersedes":"d-1"}
```

- `id`: `d-N`, assigned by the server in order, stable across carry-forward.
- `rejected`: same shape as today (`option`, `how_far` in `discussed|prototyped|built_then_removed`, optional `note`).
- `status`: `active` | `superseded`. Saving a decision with `supersedes: "d-1"` sets d-1 to `superseded` (in the new bundle's copy; parent bundles are never touched). A decision `supersedes` must name a known decision id of this lineage, else a validation error.
- The brief shows `active` decisions; superseded ones appear only under "Superseded decisions" in one line each.

### 5.5 facts.jsonl

```json
{"id":"f-1","key":"data frequency","value":"weekly","valid_from":"2026-10-01","superseded_by":"f-2"}
{"id":"f-2","key":"data frequency","value":"daily","valid_from":"2026-10-08","superseded_by":null}
```

- A fact is a small current-state statement: `key` (what it is about), `value`, `valid_from` (free text, usually a date; default is the save's `created_at`), `superseded_by` (fact id or `null`).
- Saving a fact whose `key` (case- and whitespace-insensitive) matches an active fact supersedes the old fact automatically (the old line gets `superseded_by` set). The client may also pass `superseded_by` explicitly on a fact it is retiring.
- The brief shows facts with `superseded_by == null`.

### 5.6 workspace.json

Exactly today's `workspace` object (categories `files, repos, access, connectors, tools, env_vars, skills, references`, each item with a required `status` of `still_relevant` | `done_with`), omitted categories written as empty lists. Validation is unchanged.

### 5.7 user_turns.jsonl

```json
{"n":1,"text":"first run a backtest on the last year, then write the report for Dana"}
{"n":2,"text":"also skip hourly data, it is noise"}
```

The user's key messages verbatim (after secret redaction). `n` numbers them in the order saved. They are the evidence pool for `from=user` quotes. Carried forward from the parent and appended to (duplicates after normalisation are dropped).

### 5.8 verbatim/

One file per verbatim item, named `NN-<slug>.txt` where `NN` is the 1-based position, two digits (three after 99), and `<slug>` is the label lower-cased with every run of characters outside `a-z0-9` replaced by `-`, trimmed, cut to 40 characters (`item` if empty). The position prefix makes duplicate labels safe. File bytes are the saved text UTF-8 encoded, written in binary mode with no newline translation and no added trailing newline (tabs, trailing spaces, CRLF, backticks and non-ASCII survive exactly). The label lives in `manifest.json` (`verbatim` array).

### 5.9 open_questions.json

```json
{
  "questions": [
    {"id": "q-1", "text": "Which holidays count?", "waiting_on_user": true},
    {"id": "q-2", "text": "Is 52 weeks of history enough?", "waiting_on_user": false}
  ]
}
```

`waiting_on_user: true` means the AI asked the user and the answer is pending. The brief lists these first under "Waiting on you (the user)". The old string form of `open_questions` is accepted and stored as `waiting_on_user: false`.

### 5.10 chat.json

```json
{"version": 2, "chat_name": "My Chat", "key": "my chat"}
```

Written once, on the chat's first save (never rewritten): `chat_name` is the exact name as first saved, `key` the normalised key from section 4. It is how the store tells chats apart when the folder name has a numeric suffix.

### 5.11 brief.md

The rendered brief (section 10), saved for convenience (humans, `git diff`, other tools). It is never read back: `resume_checkpoint` always renders from the data files, so deleting `brief.md` changes nothing.

## 6. events.jsonl

`chats/<chat>/events.jsonl`, append-only. Exactly one line is appended per successful save, after the bundle is written and before the commit; the file is part of the same commit. Earlier lines are never modified.

```json
{"seq":1,"ts":"2026-10-08T21:02:11+00:00","type":"checkpoint_saved","checkpoint_id":"cp-003","checkpoint_name":"forecast-v1","resumed_from":null,"client":"claude-code","tasks":3,"unfinished":2,"next_action":"t-1","renamed_from":null}
{"seq":2,"ts":"2026-10-09T09:41:05+00:00","type":"checkpoint_saved","checkpoint_id":"cp-004","checkpoint_name":"forecast-v2","resumed_from":"cp-003","client":"claude-code","tasks":4,"unfinished":2,"next_action":"t-2","renamed_from":null}
```

Event types: only **`checkpoint_saved`** exists in v2. `seq` is the line number (1-based). `renamed_from` is the requested name when Finder-style renumbering changed it (`forecast-v1` saved again becomes `forecast-v1 (1)`), else `null`. `next_action` is a task id or `null`. Lines contain no free text from the user, only ids, names and counts, so redaction cannot be bypassed through the log. Reserved for later (not written in v2): `checkpoint_resumed`, `checkpoint_deleted`.

## 7. save_checkpoint input

All old fields remain accepted with the same meaning. A call that uses only old fields still succeeds (section 12).

| Field | Status | Notes |
|---|---|---|
| `chat_name`, `checkpoint_name` | required, as today | |
| `objective`, `current_step` | required, as today | |
| `next_steps` | required **unless** `tasks` or `plan_updates` is given | old string list; becomes tasks (section 12) |
| `context`, `completed`, `notes_for_next_ai`, `last_exchange`, `workspace`, `verbatim`, `client`, `resumed_from` | optional, as today | |
| `decisions` | optional | items gain `status`, `supersedes` (section 5.4); `rejected` as today |
| `open_questions` | optional | items are strings (old) or `{text, waiting_on_user}` |
| **`tasks`** | new, optional | fresh plan; see below |
| **`plan_updates`** | new, optional | carry-forward edits to the parent's plan; needs `resumed_from`; see section 11 |
| **`user_turns`** | new, optional | list of strings: the user's key messages verbatim |
| **`facts`** | new, optional | list of `{key, value, valid_from?, superseded_by?}` |

`tasks` item: `{text, status?, from?, quote?, depends_on?, order?}` where `status` defaults to `todo`, `from` to `ai`, `depends_on` to `[]`, `order` to `10 * position` (1-based). The server assigns ids to the tasks in list order, continuing from the highest task number in the lineage: with no `resumed_from` (or a parent without a plan) the ids are `t-1`, `t-2`, ...; with `resumed_from` whose lineage's highest task number is N, they are `t-(N+1)`, `t-(N+2)`, ... so a task id is never reused within a lineage even when `tasks` replaces the plan. In a fresh `tasks` list `depends_on` is **positional**: `t-k` means the k-th item of this list (1-based). The server rewrites it to the id actually assigned, `t-(N+k)` (N = 0 for a new lineage), so the model never needs to know the parent's highest id. A `t-k` outside 1..len(list) is `unknown task`. A client-supplied `id` on a task in a fresh `tasks` list is **ignored**. `tasks` and `plan_updates` are mutually exclusive in one call (`tasks` starts a new plan, `plan_updates` edits the parent's); giving both is a validation error: `Give either tasks (a new plan) or plan_updates (changes to the parent's plan), not both.`

Validation errors (not check errors) name the field, e.g. `tasks[1].depends_on: unknown task t-9`, `tasks: dependency cycle t-1 -> t-2 -> t-1`, `tasks[0].status: must be one of todo, in_progress, done`. They are raised before anything is written.

`GitStore.save(data)` takes the same dict. `get_checkpoint` on a bundle returns both shapes (owner ruling 3): the new structured fields (`tasks`, `plan`, `next_action`, `decisions` with ids/status, `facts`, `user_turns`, `open_questions` objects, `manifest`) **and** the old flat fields (`next_steps`, `open_questions` as strings, `decisions` without ids, `verbatim`, `workspace`, ...). Where a name exists in both shapes with different structure (`decisions`, `open_questions`), the flat form keeps the name and the structured form is under `decisions_v2` / `open_questions_v2`.

The save result text (section 9) and the commit hash are returned as today.

## 8. Save-time checks

Checks run after validation and secret redaction, before any write. **All failing checks are reported together** in one error; nothing is written and no id is consumed. The MCP tool returns it as an error result (`isError`) so the chat model reads it, fixes the arguments and calls `save_checkpoint` again in the same turn. The error format:

```
Save rejected: 3 problems found. Nothing was saved. Fix all of them and call save_checkpoint again.
1. <message>
2. <message>
3. <message>
```

(`1 problem found` for one.) Messages, exactly:

1. **Quote not found.** `Task t-2 is from=user but its quote was not found in user_turns or last_exchange.user: "<quote>". Copy the user's exact words from the conversation into user_turns (or last_exchange.user) and use the same words as the quote, or set from to "ai".`
2. **Quote missing.** `Task t-2 is from=user but has no quote. Give the user's exact words as quote, or set from to "ai".`
3. **Nothing left to do.** `The plan has no unfinished task (every task is done, or there are no tasks). Add at least one task with status todo or in_progress for what happens next.`

In a fresh `tasks` list, "Task t-k" in a message is the **position** k in the list the model wrote (the same positional numbering as `depends_on`, section 7). For `plan_updates` saves the checks run on the **resulting** plan (parent tasks plus updates). Task names in messages are task ids; for new tasks without an id yet, `new task "<first 40 chars of text>"`.

**Quote matching (owner ruling 2).** Case-, whitespace- and punctuation-insensitive; the same words in the same order are required. Normalisation `norm(s)`: NFKC; `casefold()`; replace every character whose Unicode category starts with `P` (punctuation) or is a control/format character with a space; collapse whitespace runs to one space; strip. The quote passes when `norm(quote)` is a non-empty substring of `norm(turn)` for some entry in `user_turns` (this save's, plus carried-forward ones) or of `norm(last_exchange.user)`. To keep word boundaries, both sides are padded with one space before matching (`" " + norm + " "`), so `"run"` does not match inside `"truncate"`. Redaction (`redact`) is applied to quote, user turns and last exchange **before** normalisation, so a secret that is redacted on both sides still matches and a quote does not fail merely because redaction changed both sides equally.

**No heuristic on decision reasons.** There is no save-time check that guesses from free text whether a decision had alternatives (it would flag ordinary reasons). The instruction to fill `rejected` for every decision where alternatives were discussed stays in the save instructions (`schema.py`) and in the tool/field descriptions, and the eval measures the result; the code does not police it.

**Only new or changed items are checked.** Checks apply to tasks and decisions that are new or changed in this save, never to items carried forward unchanged from the parent. A parent task is "changed" only if the save's `plan_updates` touch it; its quote is not re-checked (it was checked when first saved, and the evidence pool of the parent's `user_turns` is carried forward anyway). Check 3 looks at the resulting plan as a whole.

**Which checks apply.** A save is *structured* if it contains any of `tasks`, `plan_updates`, `user_turns`, `facts`. Check 3 applies to every save (an old-only save always has tasks because `next_steps` is required, so it always passes). Checks 1 and 2 apply to structured saves only, and only to new or changed `from=user` tasks. Tasks derived from old `next_steps` (section 12) are never quote-checked, so old-style saves and the 308 existing tests are not rejected by new rules.

**Secrets** are redacted in every field (quotes, user turns, verbatim, facts, task text, ...) before checks and before writing, exactly as today; they appear in no bundle file, in `events.jsonl`, in the commit message, or in error messages (error messages echo the redacted quote).

## 9. Next action and save echo

**Rule.** The next action is the first task in `order` (ties by task number) whose `status` is `todo` and whose `depends_on` are all `done`.

- An `in_progress` task is **not** preferred and is **not** the next action: it is the work already underway and is shown in the brief under "Current step". A dependency on an `in_progress` task is unmet.
- **When none qualifies:**
  - Unfinished tasks exist but none is a ready `todo` (all blocked, or only `in_progress` ones remain): `next_action` is `null`. The brief opens with `## Next action` followed by `No task is ready. In progress: t-4 "<text>". Blocked: t-2 (waiting on t-3).` listing the in-progress tasks and each blocked todo with its unmet dependencies. The AI should finish the in-progress work or ask the user.
  - Every task is `done` (or there are none): `next_action` is `null` and the brief says `No unfinished tasks. Ask the user what to do next.` Check 3 rejects such a save, so this text is a defensive output only.
- Dependency cycles and unknown ids are validation errors at save time, so the rule never sees them.

Test case that must hold: t-1 done, t-2 todo depends_on [t-3], t-3 todo -> next action is t-3.

**Brief heading.** The stored next action stays that task (`plan.json` `next_action` is still its id and text). When the brief is rendered, if `last_exchange.assistant` contains a sentence starting with `Next step:` (otherwise `last_exchange.user`), `## Next action` leads with that sentence, through its closing period. The task line follows on the next line. The sentence is read from `core.json` `last_exchange` at render time; it is not written into `plan.json`. A last exchange with no such sentence leaves the heading as the task line alone. A closing recap that states several actions in one `Next step:` sentence is saved as that whole sentence in the unfinished task's `text`, not only its first clause; the heading rule still applies when a save splits the sentence anyway.

**Save echo.** The save result text ends with a line `Next action saved: <task text>. Correct?`; when there is no next action it ends `Next action saved: none (<reason>). Correct?` The echo is the task text, not the `Next step:` sentence. The first line is as today (new id, name, commit hash).

## 10. Brief layout

`render_brief(bundle)` is deterministic. The preamble (the "You are continuing work from checkpoint cp-004 (forecast/forecast-v2), saved ... in ..." paragraph, the "You have not seen that conversation" paragraph, and the "saved from a chat resumed from cp-003" line) is the same as today's. Sections in fixed order; an empty optional section prints `_(none recorded)_` except where stated.

1. `## Next action` — when the last exchange states a `Next step:` sentence (section 9), that sentence first. Then the computed task: `**[t-2]** Write the report`, and when it has a quote: `The user said: "then write the report for Dana"`. Or the "none" text from section 9, still after the sentence when one exists.
2. `## The user's plan` — `from=user` tasks in `order` with status, id, text, quote, dependencies: `- [t-1] (done) Run the backtest ... — user said: "first run a backtest on the last year"`. Omitted if there are none.
3. `## Other planned work` — `from=ai` tasks the same way. Omitted if there are none.
4. `## Waiting on you (the user)` — open questions with `waiting_on_user`. Omitted if none.
5. `## Objective`, `## Context`
6. `## Decisions already made` — active decisions with reason and rejected alternatives; then `### Superseded decisions` (one line each) if any.
7. `## Facts` — facts not superseded. Omitted if none.
8. `## Completed so far`
9. `## Current step` — plus in-progress tasks by id.
10. `## Open questions` — questions with `waiting_on_user` false.
11. `## Verbatim material` — fenced blocks exactly as today (fence longer than any backtick run inside, byte-exact content).
12. `## Last exchange`
13. `## Set up first` — workspace items with status `still_relevant` (as the current brief's setup list).
14. `## No longer needed` — workspace items with `done_with`, one line each with path/name and note. **Omitted when there are none.**
15. `## Notes from the previous AI`

Task ids are printed (`[t-2]`) so a later save can refer to them (section 11). The old `## Next steps` section is not printed for bundles; old flat checkpoints keep their old brief (section 12). Because the AI reads top-down, the first thing in the brief is the action and the second is the user's own plan.

## 11. Carry-forward by task id

A chat resumed from `cp-X` sees the plan with ids. When it saves, it does not rewrite the plan: it passes `resumed_from: "cp-X"` and `plan_updates`:

```json
"plan_updates": [
  {"id": "t-2", "status": "done"},
  {"id": "t-3", "status": "in_progress"},
  {"text": "Send the report to Dana", "from": "user", "quote": "then send it to Dana", "depends_on": ["t-2"]}
]
```

- An item with `id` edits the parent's task: only `status`, `depends_on` and `order` can change. Its `text`, `from` and `quote` are fixed (the harness lesson: status flips, no rewriting). An item that gives `text` with an `id` is a validation error: `plan_updates[0]: task t-2 cannot be reworded; only status, depends_on and order can change. Add a new task instead.`
- An item without `id` is a new task: `text` required, other fields as in `tasks`. It gets the next unused number after the lineage's highest task number (the parent's tasks, including done ones, so `t-N` is never reused). `depends_on` may name existing ids or ids that new tasks in this list will receive (assigned in list order).
- Unknown id: `plan_updates[1]: unknown task id t-9 (parent cp-X has t-1, t-2, t-3).` Nothing is written.
- `plan_updates` without `resumed_from`: `plan_updates needs resumed_from: pass the id of the checkpoint this chat was resumed from.`
- The new `plan.json` keeps **all** parent tasks (ids, text, from, quote, order) with updates applied, plus the new tasks. Then the checks (section 8) and the next action run on the resulting plan.

**Everything else carries forward** from the parent unless the save supplies its own: `decisions` (parent's kept, new ones appended, `supersedes` applied; supplying `decisions` adds, it does not replace), `facts` (same, with automatic supersede by key), `workspace` (merged by category and key; a supplied item replaces the parent's item with the same key), `user_turns` (appended, deduplicated), `open_questions` (supplying the list replaces the parent's, because questions are answered and disappear), `verbatim` (replaced if supplied, otherwise carried). Scalar sections (`objective`, `current_step`, ...) are always supplied by the save.

**When carry-forward applies (owner ruling, F-005 criterion 4).** Only a resumed save that uses the structured fields (`tasks`, `plan_updates`, `user_turns` or `facts`) carries forward the sections it does not supply and merges the ones it does, as described above. An **old-fields-only** resumed save (`next_steps` etc.) behaves exactly as it did before v2 carry-forward: nothing is carried, and its sections are exactly what it supplies. Adding any one of the four structured fields, non-empty, switches carrying on; an empty `[]` for any of them counts as not given and does not (the same on the store, CLI and MCP paths; an explicit `tasks: []` still reaches the "no unfinished task" check). The plan of an old-fields-only save is its `next_steps` (a fresh plan); task ids still continue from the lineage max. In a carrying save, `decisions`/`facts` ids continue after the parent's when merged (`d-(P+1)`, ...), so `supersedes` / `superseded_by` there name lineage ids (parent ids or earlier ones in the list), not list positions; `user_turns` are deduplicated after normalisation (`norm`, section 8) and the parent's turns are part of the quote evidence pool; for `open_questions` and `verbatim`, "supplied" means the field is present and not null (an explicit `[]` replaces; for `decisions` an empty list counts as not supplied). In `plan_updates`, `depends_on` ids are real task ids (as shown in the brief), not positions. Checks 1 and 2 apply to the new tasks of `plan_updates` only (label `New task "<first 40 chars>"`); parent tasks keep their `raw` field.

**Parent is an old flat checkpoint.** Its `next_steps` are first converted to tasks (section 12, ids t-1..t-n), then `plan_updates` apply to that plan. Its decisions get ids d-1.., `open_questions` get q-1... in saved order.

The events line records `resumed_from`. If the parent id does not exist, the save fails with the existing not-found error.

## 12. Old-format compatibility

- **Old flat files** `checkpoints/cp-NNN.json` are read in place by `get`, `list`, `resolve` and `resume_checkpoint`. They are never rewritten, renamed, moved or migrated, and nothing in a bundle save touches them (their file hash is unchanged after later saves).
- **Resume of an old file** renders with the old `render_brief` path, byte-identical to today. Golden test: `tests/fixtures/old_format_cp.json` resumed gives exactly `tests/fixtures/old_format_brief.golden.md`.
- **Mixed store**: `list` merges old files and bundles ordered by id, newest first; `resolve`/renumbering look at both; ids are global (section 4). A corrupt bundle (unreadable manifest, bad JSON in a data file, higher `version`) is skipped by `list` and `resolve` like a corrupt flat file is today.
- **Old-style input, new storage.** Every save writes a bundle. Old fields map as: `next_steps` -> tasks, in order, `order` 10, 20, ...; a step starting with `User's plan:` becomes `from=user` with the prefix removed from `text` and `quote` set to that text (these derived quotes are not checked); the task also keeps the original step in a `raw` field so the flat view returns `next_steps` byte for byte (these derived quotes are not checked); other steps are `from=ai`; all `todo`. `decisions` -> decisions.jsonl with ids, `status: active`. `open_questions` strings -> `waiting_on_user: false`. `completed`, `context`, `notes_for_next_ai`, `last_exchange` -> `core.json`. `user_turns` is derived from `last_exchange.user` when non-empty so quote checks on later resumes have evidence; otherwise empty.
- **`get_checkpoint`** returns both shapes for bundles (section 7); for old flat files it returns the old dict unchanged.
- The `Checkpoint` dataclass and `Checkpoint.from_dict` keep working for old data; the bundle loader builds the flat `Checkpoint` view from the bundle for callers that still want it.

## 13. Owner rulings (decisions.md, binding)

1. **Eval retry.** When save checks reject a checkpoint in the eval, the model gets **one** retry with the error messages (mirrors the in-chat fix-in-the-same-turn flow). Whether the retry was needed is recorded in `results.json` (per scenario `save_retry: true|false`, plus `save_errors` for the first attempt). If the retry also fails, the failure is recorded (`save_failed: true`, errors kept) and the scenario's checkpoint handover is scored as failed rather than aborting the suite.
2. **Quote check** is case-, whitespace- and punctuation-insensitive; the same words are required (section 8).
3. **`get_checkpoint` on a bundle returns both** the new structured fields and the old flat fields (section 7).
4. **Resumed under a different chat_name**: the bundle goes into the **new** name's chat folder, linked to the parent by `resumed_from` / manifest (section 4).

## 14. Eval changes

Scope of the eval kit changes (F-006), all offline-testable:

- `compaction_system_prompt()` is built from the same schema source as the MCP tool: `schema.py` holds the field descriptions for the new fields (`tasks`, `plan_updates`, `user_turns`, `facts`, decision `status`/`supersedes`, open-question `waiting_on_user`), the tool and the prompt both read them, and a test asserts each tool field description appears in the prompt.
- The checkpoint handover goes through the bundle path: the model's JSON is passed to `GitStore.save` in a temp dir, then `resume` renders the brief. Save-check errors are recorded in the result (`save_errors`, `save_retry`, `save_failed`), not raised. One retry with the error text per owner ruling 1.
- `FakeModel`'s compaction output uses the new fields: tasks with `from=user` quotes copied verbatim from the transcript, `user_turns`, workspace with `done_with` items, and passes the checks.
- The old path stays available behind a flag (`--checkpoint-format flat`) so earlier runs can be reproduced.
- `checkpoint-eval suite datasets/handover-v2/*.json --model fake --out <tmp>` completes offline, writing `results.json` and `results.md` for all 6 scenarios.

**Real-model target (manual run, not an offline test).** Run the real suite on handover-v2 with the same model as the baseline (anthropic/claude-haiku-5.5) and compare against `eval-runs/2026-10-09-handover-v2-haiku`:

| Metric | Baseline | Target |
|---|---|---|
| Next step (checkpoint handover) | 50% | **>= 90%** |
| Key-fact recall (checkpoint handover) | 88% | **>= 88%** (must not drop) |
| Contradictions | 2 | not more than baseline |
| Verbatim exact | 100% | 100% |
| Stale use | 0% | 0% |

Record the run under `eval-runs/` with a README row. The branch is pushed only if next step >= 90% and recall >= 88%.

## 15. Out of scope

- SQLite search index and `ask_checkpoint` (the events log and bundle files are shaped so an index can be built later).
- Embeddings and semantic search.
- MCP sampling (the server never calls a model).
- Online backends (hosted sync, remote stores).
- Migrating or rewriting old flat checkpoints.
- Deleting or editing saved checkpoints; `checkpoint_resumed` / `checkpoint_deleted` events.
