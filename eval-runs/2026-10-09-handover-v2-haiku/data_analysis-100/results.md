Scenario: data_analysis-100 | model: anthropic/claude-haiku-5.5 | 100 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 86% | 0 | 100% | 0% | 0% | 3269 |
| summary | ok | 88% | 0 | 100% | 0% | 0% | 1094 |
| full_history | ok | 97% | 0 | 100% | 0% | 100% | 4567 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 72% | 85% | 40% | 65% | 100% | 0 |
