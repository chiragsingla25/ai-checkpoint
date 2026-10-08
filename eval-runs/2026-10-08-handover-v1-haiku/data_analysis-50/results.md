Scenario: data_analysis-50 | model: anthropic/claude-haiku-5.5 | 50 messages, 11 probes

| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |
|---|---|---|---|---|---|---|---|
| checkpoint | ok | 83% | 0 | 100% | 100% | 100% | 2816 |
| summary | ok | 70% | 1 | 67% | 100% | 100% | 896 |
| full_history | ok | 95% | 0 | 100% | 100% | 100% | 2646 |

Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):

| capture recall | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |
|---|---|---|---|
| 39% | 47% | 100% | 0 |
