Scenario: coding-20 | model: anthropic/claude-haiku-5.5 | 20 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 88% | 0 | 100% | 0% | 0% | 3303 |
| summary | ok | 76% | 1 | 100% | 100% | 0% | 1067 |
| full_history | ok | 97% | 1 | 100% | 100% | 100% | 1818 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 56% | 53% | 100% | 0 |
