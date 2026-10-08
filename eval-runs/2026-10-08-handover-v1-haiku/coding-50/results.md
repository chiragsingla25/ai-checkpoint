Scenario: coding-50 | model: anthropic/claude-haiku-5.5 | 50 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | n/a | n/a | n/a | n/a | n/a | 3084 |
| summary | ok | 73% | 1 | 100% | 0% | 0% | 1244 |
| full_history | ok | 91% | 0 | 100% | 100% | 100% | 3081 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 61% | 55% | 91% | 0 |
