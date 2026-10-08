Scenario: coding-100 | model: anthropic/claude-haiku-5.5 | 100 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 97% | 0 | 100% | 0% | 100% | 3548 |
| summary | ok | 86% | 0 | 100% | 0% | 100% | 1091 |
| full_history | ok | 97% | 0 | 100% | 0% | 100% | 5174 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 83% | 92% | 60% | 76% | 100% | 0 |
