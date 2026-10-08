Scenario: data_analysis-20 | model: anthropic/claude-haiku-5.5 | 20 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 88% | 1 | 100% | 0% | 100% | 2406 |
| summary | ok | 71% | 2 | 67% | 0% | 0% | 747 |
| full_history | ok | 97% | 0 | 100% | 0% | 100% | 1541 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 78% | 92% | 40% | 86% | 100% | 0 |
