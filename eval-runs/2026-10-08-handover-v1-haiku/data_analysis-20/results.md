Scenario: data_analysis-20 | model: anthropic/claude-haiku-5.5 | 20 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 88% | 1 | 100% | 100% | 100% | 2609 |
| summary | ok | 74% | 1 | 67% | 100% | 0% | 938 |
| full_history | ok | 95% | 0 | 100% | 100% | 100% | 1494 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 61% | 79% | 100% | 0 |
