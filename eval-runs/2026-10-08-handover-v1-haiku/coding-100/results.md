Scenario: coding-100 | model: anthropic/claude-haiku-5.5 | 100 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 88% | 0 | 100% | 100% | 100% | 3334 |
| summary | ok | 97% | 0 | 100% | 0% | 100% | 1255 |
| full_history | ok | 94% | 0 | 100% | 100% | 100% | 5134 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 56% | 59% | 100% | 0 |
