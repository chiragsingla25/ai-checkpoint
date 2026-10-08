Summary of the previous chat:

## Summary: dispatch-relay duplicate-notification fix

**Repo and context**
- Repo: `~/work/dispatch-relay`, branch `fix/webhook-dedupe`, last commit `fb04dde` ("Verify webhook signature before parsing").
- Flask service that receives delivery-status webhooks from the carrier and texts customers.
- Problem: when the endpoint is slow, the carrier retries, and customers get the same "out for delivery" text two or three times. Support logged 26 complaints this week (thread SUP-2464).
- Tools: pytest, ruff. The GitHub connector is attached, but I have not reviewed the PR.

**Code facts**
- The webhook handler was originally in `app/handlers.py`. The user has since renamed it to `app/webhooks.py` and updated the import in `app/__init__.py`. Use `app/webhooks.py` from here on.
- The original handler calls `request.get_json()`, then `verify_signature(payload, ...)` on the parsed dict, then `notify_customer(...)`, and returns 200. Nothing records which events were handled.
- Payloads carry `event_id` (e.g. `evt_9f3a`), which is the dedupe key.
- Local signature checks fail. Suspected cause: the HMAC is computed over re-serialised parsed JSON rather than the raw bytes the carrier signed. The planned fix is to verify over `request.get_data()` and parse JSON afterwards. **Not confirmed as implemented.**
- The user pasted a secret-looking value (`sk-fake-...`) into the chat. The assistant advised rotating it if it is real. Worth confirming.
- Env vars involved: `CARRIER_WEBHOOK_SECRET`, `DATABASE_URL` (local Postgres).

**Decisions made**
- **Dedupe storage:** Postgres table `webhook_events` with `event_id` as a unique key and `received_at`. Redis was ruled out (not available, and the platform team will not provision it before next quarter). Celery was ruled out (needs a broker).
- **Insert statement:** `INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;`. Check `cur.rowcount`: 1 means new and process the event, 0 means duplicate and skip.
- **Retention:** delete rows older than **48 hours**. The user corrected an earlier 24-hour suggestion after checking the carrier docs, which retry for up to 48 hours. Cleanup is a scheduled `DELETE ... WHERE received_at < now() - interval '48 hours'`.
- **Async sending:** module-level `ThreadPoolExecutor(max_workers=8)`. The handler verifies the signature, records the event id, submits `notify_customer` to the pool, and returns **202** immediately. Duplicates return **200** without notifying, so the carrier stops retrying. Accepted trade-off: queued work is lost if the process dies, and the carrier's retry covers that now that duplicates are harmless.
- **Replay protection:** reject webhooks whose timestamp is more than **324 seconds** old.
- **Unknown status values:** log a warning with the raw status string, return 200, and skip the customer notification.
- **Logging:** log identifiers and failure reasons, not full bodies. Use lazy `logger.info('... %s', x)` formatting.

**Tests**
- Three useful sample payloads were copied into `tests/fixtures/`. Do **not** look in `~/scratch/dispatch-relay-carrier-samples/` again.
- ngrok is no longer needed. Tests use fixtures and make no network calls.
- Run dedupe tests with `pytest -q tests/test_webhooks.py -k dedupe`. Name dedupe tests so `-k dedupe` selects them.
- Follow the python-testing skill conventions: one behaviour per test, shared fixtures, no network.
- Priority test: deliver the same event twice and assert one notification.

**Next steps**
1. Write `migrations/0029_add_event_dedupe.sql` creating `webhook_events` with a unique `event_id`. The number 0029 has not been checked against the existing migrations folder.
2. Apply the migration on staging.
3. Add the replay test that delivers the same event twice.
4. Confirm whether the raw-body HMAC fix is in place, and check the local signature failure.
5. Add the `webhook_events` cleanup job (48-hour retention).
6. Review the PR via the GitHub connector and keep ruff clean.
7. Confirm whether the pasted secret needs rotating.

**Open questions**
- Whether the raw-body signature fix has landed.
- Whether a CHANGELOG exists (the assistant suggested one line only if it does).
- Whether a support-queue watch is planned for about a week after deploy to confirm the complaints stop.
