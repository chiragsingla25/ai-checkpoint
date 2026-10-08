# Decisions

## F-001 criterion "Full suite passes" (QA objection, attempt 1)
- Who raised: QA. The guard test tests/test_metrics.py::test_product_code_unchanged (from an earlier eval-only run) fails whenever product code is uncommitted, so an intentional product change can only pass after commit.
- Ruling (orchestrator, mechanical; reported to Chirag): accept QA's proposed wording — the suite must be fully green after the orchestrator commits F-001; the guard may fail only while schema.py is uncommitted. Verified by running the full suite after the commit.
- Reason: the criterion was unsatisfiable as written for an intentional product change; no rework needed.
