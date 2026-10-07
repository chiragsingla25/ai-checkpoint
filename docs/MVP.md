# AI Checkpoint
## MVP Project Development Document

**Status:** Development Ready  
**Version:** 0.1  
**Objective:** Build and validate a portable AI-work checkpointing system.

---

# 1. Project Overview

## 1.1 Product

**AI Checkpoint** is a system that allows users to save the current state of AI-assisted work as a versioned checkpoint and later resume that work from a new AI conversation.

The core concept is:

```text
AI Conversation
      ↓
Continuous Capture
      ↓
Current Working State
      ↓
Save Checkpoint
      ↓
Git Commit
      ↓
New Conversation
      ↓
Resume Checkpoint
      ↓
Continue Work
```

The product should eventually allow work to move between AI providers such as:

- ChatGPT
- Claude
- Gemini
- Codex
- Claude Code
- Other AI coding/work agents

The MVP will **not** attempt to support all providers.

---

# 2. Problem

Long AI conversations accumulate valuable context:

- Requirements
- Decisions
- Reasoning
- Code
- Files
- Tool results
- Completed work
- Open questions
- Next steps

Starting a new conversation usually means losing much of this working context.

Users may want a new conversation because:

- The conversation has become very large.
- Context has become noisy.
- They want to switch models.
- They want to explore a different approach.
- The current conversation has become slow.
- They want to branch the work.
- They want to continue on another machine.

AI Checkpoint treats AI work more like software development:

```text
Conversation → Checkpoint → Branch → Resume
```

Similar to:

```text
Code → Git Commit → Branch → Checkout
```

---

# 3. Product Vision

> **Save your AI work like a Git commit. Resume it from anywhere.**

Long-term vision:

> Make AI-assisted work portable, versioned, branchable and resumable across AI providers.

---

# 4. MVP Goal

The MVP has one job:

> **Prove that a user can work with an AI, save a checkpoint, start a completely new conversation, restore the checkpoint, and continue the work without having to reconstruct the previous conversation manually.**

Everything else is secondary.

---

# 5. MVP Scope

## Must Have

### Capture

- Capture user messages.
- Capture assistant messages.
- Preserve message ordering.
- Preserve timestamps where available.
- Preserve conversation/session ID.
- Maintain a local working buffer.
- Capture continuously during the conversation.

### Checkpoint

- Create named checkpoint.
- Store conversation state.
- Store checkpoint metadata.
- Persist checkpoint locally.
- Commit checkpoint to Git.

### Resume

- List available checkpoints.
- Select a checkpoint.
- Load checkpoint.
- Construct resumable context.
- Provide that context to a new AI conversation.

### Versioning

- Git repository.
- One Git commit per saved checkpoint.
- Checkpoint IDs.
- Basic checkpoint history.

---

# 6. Explicitly Out of Scope for MVP

Do **not** build these initially:

- Cloud backend
- User accounts
- Billing
- Team collaboration
- Web dashboard
- GitHub integration
- Vector database
- Embeddings
- Complex RAG
- Automatic branching
- Multi-user permissions
- Enterprise authentication
- Advanced UI
- Mobile application
- Full ChatGPT/Claude/Gemini support
- Perfect conversation compression
- Automated browser control
- Playwright dependency

The MVP should be local-first.

---

# 7. Recommended MVP Architecture

```text
                    ┌──────────────────────┐
                    │      AI Client       │
                    │                      │
                    │ Claude Code / Codex  │
                    └──────────┬───────────┘
                               │
                               │ messages / events
                               ▼
                    ┌──────────────────────┐
                    │    Capture Adapter   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Universal Conversation│
                    │       Format         │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Checkpoint Engine   │
                    └──────────┬───────────┘
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
              Local Storage             MCP
                     │                   │
                     └─────────┬─────────┘
                               ▼
                         Git Repository
```

---

# 8. Architectural Components

## 8.1 Capture Adapter

Responsible for obtaining conversation events from a specific AI client.

For MVP:

**Choose one provider.**

Recommended first targets:

1. Claude Code
2. Codex

These are preferable to ChatGPT web for the first prototype because local session data and lifecycle mechanisms make capture significantly easier.

The adapter should expose a provider-independent interface.

Example:

```python
class CaptureAdapter:

    def start_session(self, session_id):
        pass

    def capture_message(self, message):
        pass

    def end_session(self, session_id):
        pass
```

The exact implementation can differ by provider.

---

# 9. Universal Conversation Format

All providers should eventually be normalized into the same internal format.

Example:

```json
{
  "conversation_id": "abc123",
  "provider": "claude_code",
  "created_at": "2026-10-07T10:00:00Z",
  "messages": [
    {
      "id": "m001",
      "role": "user",
      "content": "Build a forecasting model",
      "timestamp": "2026-10-07T10:00:01Z"
    },
    {
      "id": "m002",
      "role": "assistant",
      "content": "We can build this using XGBoost...",
      "timestamp": "2026-10-07T10:00:05Z"
    }
  ]
}
```

The checkpoint engine should not care whether the source was:

```text
ChatGPT
Claude
Gemini
Codex
Claude Code
```

It should consume the normalized format.

---

# 10. Continuous Capture

This is an important architectural requirement.

The system should **not wait until the user says "Save Checkpoint" to retrieve the conversation**.

Instead:

```text
Message 1
   ↓
Capture

Message 2
   ↓
Capture

Message 3
   ↓
Capture

...

Message N
   ↓
Capture
```

The local working buffer therefore always represents the current conversation.

When the user chooses:

```text
Save Checkpoint
```

the system simply commits the current state.

---

# 11. Checkpoint Model

A checkpoint represents a recoverable point in AI work.

Example:

```json
{
  "checkpoint_id": "cp-001",
  "name": "Initial forecasting implementation",
  "conversation_id": "abc123",
  "provider": "claude_code",
  "created_at": "2026-10-07T11:30:00Z",

  "messages": [],

  "state": {
    "objective": "",
    "decisions": [],
    "completed_work": [],
    "open_questions": [],
    "next_steps": []
  },

  "artifacts": [],

  "metadata": {}
}
```

For the MVP, **raw messages are the source of truth**.

The structured `state` section can initially be simple or generated later.

---

# 12. Checkpoint Storage

Recommended initial structure:

```text
.ai-checkpoint/
│
├── config.json
│
├── conversations/
│   └── abc123.json
│
├── checkpoints/
│   ├── cp-001.json
│   ├── cp-002.json
│   └── cp-003.json
│
├── state/
│   └── current.json
│
└── artifacts/
    └── ...
```

Git repository:

```text
.ai-checkpoint/
        ↓
       Git
```

Each checkpoint creates a commit.

Example:

```text
checkpoint: cp-001
checkpoint: cp-002
checkpoint: cp-003
```

---

# 13. Git Requirements

The MVP only needs local Git.

Required operations:

```text
git init
git add
git commit
git log
git show
```

Checkpoint creation:

```text
Capture current state
        ↓
Write checkpoint JSON
        ↓
git add
        ↓
git commit
```

Example commit:

```text
checkpoint: cp-001 - forecasting architecture
```

GitHub/GitLab/Bitbucket integration is not required initially.

---

# 14. MCP Server

The MCP server should expose a minimal API.

## MVP tools

### `save_checkpoint`

Save current captured state.

Input:

```json
{
  "name": "Forecasting architecture"
}
```

Output:

```json
{
  "checkpoint_id": "cp-001",
  "commit": "abc123"
}
```

---

### `list_checkpoints`

Return available checkpoints.

Example:

```json
[
  {
    "id": "cp-001",
    "name": "Forecasting architecture",
    "created_at": "..."
  },
  {
    "id": "cp-002",
    "name": "Model implementation",
    "created_at": "..."
  }
]
```

---

### `get_checkpoint`

Retrieve checkpoint metadata/state.

Input:

```json
{
  "checkpoint_id": "cp-001"
}
```

---

### `resume_checkpoint`

Prepare checkpoint context for continuation.

Input:

```json
{
  "checkpoint_id": "cp-001"
}
```

Output should contain enough context for the AI to continue the work.

---

# 15. Resume Strategy

The first implementation should be simple.

When resuming:

```text
Checkpoint
    ↓
Read messages
    ↓
Build continuation context
    ↓
Give context to new AI
```

Example generated resume context:

```text
You are continuing work from checkpoint cp-001.

PROJECT OBJECTIVE:
Build a customer churn prediction system.

PREVIOUS DECISIONS:
- Use XGBoost as the primary model.
- Use F1 score as the main evaluation metric.
- Store features in...

COMPLETED:
- Data ingestion
- Feature engineering
- Baseline model

CURRENT STATE:
Model training is complete.

NEXT STEPS:
1. Evaluate model.
2. Tune hyperparameters.
3. Create deployment pipeline.

RELEVANT CONVERSATION HISTORY:
...
```

Do not attempt sophisticated context compression initially.

First prove that raw history works.

---

# 16. MVP Development Phases

## Phase 1 — Local Capture

Goal:

```text
AI conversation
      ↓
local JSON
```

Tasks:

- Select first provider.
- Understand its session/event format.
- Implement capture adapter.
- Capture user messages.
- Capture assistant messages.
- Persist locally.
- Test restart/recovery.

### Exit criteria

A 50-message conversation can be reconstructed exactly from the captured data.

---

# Phase 2 — Checkpoint Engine

Goal:

```text
local conversation
       ↓
checkpoint
```

Tasks:

- Define checkpoint schema.
- Generate checkpoint IDs.
- Save checkpoint JSON.
- Add metadata.
- List checkpoints.
- Retrieve checkpoints.

### Exit criteria

A conversation can produce multiple independent checkpoints.

---

# Phase 3 — Git

Goal:

```text
checkpoint
    ↓
Git commit
```

Tasks:

- Initialize repository.
- Add checkpoint files.
- Commit automatically.
- Read Git history.
- Retrieve previous checkpoint versions.

### Exit criteria

Every saved checkpoint produces a reproducible Git commit.

---

# Phase 4 — Resume

Goal:

```text
Checkpoint
     ↓
New AI conversation
     ↓
Continue work
```

Tasks:

- Load checkpoint.
- Generate resume context.
- Provide context to new AI.
- Validate continuation.

### Exit criteria

The new conversation can correctly explain the previous work and continue it.

---

# Phase 5 — MCP

Expose the checkpoint functionality through MCP.

Implement:

```text
save_checkpoint
list_checkpoints
get_checkpoint
resume_checkpoint
```

### Exit criteria

The AI can interact with the checkpoint system through MCP.

---

# Phase 6 — Artifact Support

Only after conversation checkpointing works.

Support:

```text
Code
Files
Documents
Tool outputs
```

Example:

```text
Checkpoint
├── conversation
├── project state
├── model.py
├── requirements.txt
└── README.md
```

### Exit criteria

A resumed AI can understand and modify the artifacts associated with a checkpoint.

---

# 17. Testing Strategy

## Test 1 — Capture Reliability

Create a 50-message conversation.

Verify:

- Every user message captured.
- Every assistant message captured.
- Correct ordering.
- No duplicates.
- No missing messages.
- Correct timestamps where available.
- Correct session ID.

**Target: 100% message recovery.**

---

# 18. Test 2 — Multiple Checkpoints

Create:

```text
Messages 1–20
    ↓
cp-001

Messages 21–40
    ↓
cp-002

Messages 41–60
    ↓
cp-003
```

Verify:

- cp-001 contains the correct state.
- cp-002 contains the correct state.
- cp-003 contains the correct state.
- Earlier checkpoints remain unchanged.

---

# 19. Test 3 — Resume Accuracy

Create a meaningful project conversation.

Example:

```text
Build a Python customer churn prediction system.
```

Work through:

- Requirements
- Architecture
- Implementation
- Debugging
- Decisions

Save checkpoint.

Start a completely new conversation.

Resume.

Ask:

> What were we working on, what decisions did we make, what has been completed, and what should we do next?

Evaluate:

| Capability | Pass |
|---|---|
| Understand objective | ☐ |
| Understand decisions | ☐ |
| Understand completed work | ☐ |
| Understand current state | ☐ |
| Identify next steps | ☐ |
| Continue implementation | ☐ |
| Avoid contradicting history | ☐ |

---

# 20. Test 4 — Checkpoint vs Summary

Compare two approaches.

### A — Normal summary

```text
Conversation
     ↓
Summary
     ↓
New AI
```

### B — AI Checkpoint

```text
Conversation
     ↓
Checkpoint
     ↓
New AI
```

Give both systems the same continuation task.

Measure:

- Correctness
- Context retention
- Number of clarification questions
- Repeated work
- Incorrect assumptions
- Ability to continue implementation

This test determines whether the checkpoint concept provides meaningful value over ordinary summarization.

---

# 21. Test 5 — Long Conversations

Test:

```text
50 messages
100 messages
200 messages
500 messages
1,000 messages
```

Measure:

- Storage size
- Resume latency
- Context size
- Token usage
- Continuation quality

Later experiment with:

```text
Old history → compressed
Recent history → raw
Important decisions → structured
Artifacts → separate files
```

---

# 22. Test 6 — Artifact Continuity

Create code during a conversation.

Save checkpoint.

Start new conversation.

Resume checkpoint.

Ask the AI to modify the code.

Verify that it understands:

- What the code does.
- Why it exists.
- Previous implementation decisions.
- Current version.
- Required next change.

---

# 23. Test 7 — Cross-Provider Continuation

This is a later MVP validation test.

Example:

```text
Claude
   ↓
Checkpoint
   ↓
ChatGPT
```

Then:

```text
ChatGPT
   ↓
Checkpoint
   ↓
Claude
```

Initially, this can be tested manually.

The goal is to answer:

> Can work created with one AI provider be continued effectively by another provider?

If yes, the cross-provider concept is validated.

---

# 24. Success Criteria

The MVP is considered successful if:

### Core

- [ ] Conversation can be continuously captured.
- [ ] Conversation can be stored locally.
- [ ] Checkpoint can be created.
- [ ] Checkpoint can be committed to Git.
- [ ] Multiple checkpoints can coexist.
- [ ] Previous checkpoints can be retrieved.
- [ ] New conversation can resume a checkpoint.
- [ ] AI can correctly understand previous work.
- [ ] AI can continue the work.

### Quality

- [ ] No missing messages.
- [ ] No duplicate messages.
- [ ] Checkpoints are reproducible.
- [ ] Resume process is reliable.
- [ ] Resume doesn't require manually reconstructing the project.

### Product validation

- [ ] Checkpoint performs better than a simple summary for meaningful tasks.
- [ ] Users can understand the checkpoint concept immediately.
- [ ] The workflow feels similar to a Git commit/resume workflow.

---

# 25. Future Architecture

Once the core engine works:

```text
                         AI Checkpoint
                              │
              ┌───────────────┴───────────────┐
              │                               │
        Capture Layer                    MCP Server
              │                               │
       ┌──────┼──────┐                        │
       │      │      │                        │
   ChatGPT Claude Gemini                  Checkpoint
       │      │      │                     Engine
       │      │      │                        │
       └──────┼──────┘                        │
              │                               │
              └──────────────┬────────────────┘
                             ↓
                       Universal State
                             ↓
                        Git / Storage
```

Provider adapters:

```text
Claude Code → local session adapter
Codex       → lifecycle/session adapter
ChatGPT     → browser/API capture adapter
Claude Web  → browser/API capture adapter
Gemini      → browser/API capture adapter
```

The provider-specific capture mechanism should remain isolated from the checkpoint engine.

---

# 26. Important Architectural Principle

**Do not make the MCP server responsible for provider-specific conversation capture.**

Instead:

```text
Provider
   ↓
Provider Adapter
   ↓
Universal Format
   ↓
Checkpoint Engine
   ↓
MCP / Git
```

This keeps the core product provider-independent.

ChatGPT's lack of a native transcript API should therefore not affect the core architecture.

---

# 27. Security Considerations

The system will potentially capture highly sensitive information.

The MVP should therefore be:

**Local-first.**

Requirements:

- No conversation data sent to a central server.
- No API keys stored in checkpoint files.
- No authentication tokens stored in Git.
- `.gitignore` for sensitive files.
- Clear separation between workspace data and credentials.
- User controls where the Git repository is stored.

Never automatically commit:

```text
API keys
Passwords
OAuth tokens
Browser cookies
Private credentials
```

---

# 28. Initial Repository Structure

Suggested implementation:

```text
ai-checkpoint/
│
├── README.md
├── pyproject.toml
│
├── src/
│   └── checkpoint/
│       ├── capture/
│       │   ├── base.py
│       │   └── provider.py
│       │
│       ├── checkpoint/
│       │   ├── models.py
│       │   ├── engine.py
│       │   └── storage.py
│       │
│       ├── git/
│       │   └── repository.py
│       │
│       ├── resume/
│       │   └── context.py
│       │
│       └── mcp/
│           └── server.py
│
├── tests/
│   ├── test_capture.py
│   ├── test_checkpoint.py
│   ├── test_git.py
│   └── test_resume.py
│
└── examples/
```

This structure can change once implementation begins.

---

# 29. First Development Sprint

Do **not** start with MCP.

Start with the underlying engine.

### Step 1

Create:

```text
Conversation
```

object.

### Step 2

Create:

```text
Message
```

object.

### Step 3

Create:

```text
Checkpoint
```

object.

### Step 4

Implement local JSON persistence.

### Step 5

Implement:

```text
capture_message()
```

### Step 6

Implement:

```text
create_checkpoint()
```

### Step 7

Implement Git commits.

### Step 8

Implement:

```text
load_checkpoint()
```

### Step 9

Implement resume-context generation.

### Step 10

Run the end-to-end test:

```text
Capture
 → Save
 → Git
 → New conversation
 → Resume
 → Continue
```

Only once this works should MCP become the interface layer.

---

# 30. First Technical Milestone

The first milestone is intentionally tiny:

```text
$ checkpoint init

$ checkpoint capture

$ checkpoint save "forecasting-v1"

Checkpoint created:
    cp-001

Git commit:
    a83f91c

$ checkpoint list

cp-001   forecasting-v1

$ checkpoint resume cp-001

Checkpoint loaded.
```

If this works locally, the foundation is real.

---

# 31. Product Development Rule

Throughout development, keep asking one question:

> **Does this make AI work easier to stop, save, move, and continue?**

If not, it probably does not belong in the MVP.