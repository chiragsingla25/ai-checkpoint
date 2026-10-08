Scenario: data_analysis-50 | model: anthropic/claude-haiku-5.5 | 50 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 95% | 0 | 100% | 0% | 100% | 2912 |
| summary | ok | 74% | 0 | 67% | 0% | 100% | 936 |
| full_history | ok | 100% | 0 | 100% | 0% | 100% | 2693 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|---|---|
| 78% | 92% | 40% | 71% | 100% | 0 |
