Scenario: data_analysis-100 | model: anthropic/claude-haiku-5.5 | 100 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 83% | 1 | 100% | 100% | 0% | 2675 |
| summary | ok | 83% | 1 | 100% | 100% | 0% | 1213 |
| full_history | ok | 92% | 0 | 100% | 100% | 100% | 4520 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 61% | 73% | 100% | 0 |
