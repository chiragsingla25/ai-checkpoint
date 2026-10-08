Scenario: coding-20 | model: anthropic/claude-haiku-5.5 | 20 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 77% | 1 | 100% | 0% | 0% | 3055 |
| summary | ok | 76% | 1 | 100% | 0% | 0% | 1252 |
| full_history | ok | 97% | 0 | 100% | 0% | 100% | 1857 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 94% | 100% | 80% | 79% | 93% | 0 |
