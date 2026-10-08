Scenario: coding-50 | model: anthropic/claude-haiku-5.5 | 50 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 85% | 0 | 100% | 0% | 0% | 3112 |
| summary | ok | 72% | 2 | 100% | 0% | 0% | 1043 |
| full_history | ok | 100% | 0 | 100% | 0% | 100% | 3121 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 89% | 92% | 80% | 71% | 87% | 0 |
