Summary of the previous chat:

## Summary: dispatch-relay duplicate-text fix

**Repo and context**
- Repo: `~/work/dispatch-relay` (Flask), branch `fix/webhook-dedupe`, last commit `fb04dde` "Verify webhook signature before parsing".
- Bug: when the endpoint is slow, the carrier retries webhooks, so customers get the same "out for delivery" SMS two or three times. Support logged 26 complaints this week (thread SUP-2464).
- Each payload has an `event_id` such as `evt_9f3a`. This is the dedupe key.
- The handler was in `app/handlers.py`. The user renamed it to `app/webhooks.py` and updated the import in `app/__init__.py`. Use the new name.
- Tooling: pytest, ruff. The GitHub and Sentry connectors are available. The user used Sentry to pull failing deliveries.
- The user copied three useful carrier payloads into `tests/fixtures/`. Do not look in `~/scratch/dispatch-relay-carrier-samples/`. ngrok is not needed.

**Original handler (before changes)**
```python
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```
The handler sends the SMS synchronously, which is why the carrier times out and retries. It also has no memory of processed events.

**Decisions made**
- **Dedupe store:** a Postgres table `webhook_events` with a unique constraint on `event_id`. No Redis, because the platform team won't provision it before next quarter. Celery is also out, since it needs a broker.
- **Insert:** `INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;`. Check `cur.rowcount`: 1 means new, so process the event; 0 means duplicate, so skip it.
- **Retention:** keep dedupe rows for **48 hours**, then delete them. The user corrected an earlier 24-hour figure after checking the carrier docs, which say retries continue for up to 48 hours. A scheduled job runs `DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours';`. This job is not built yet.
- **Async send:** a module-level `ThreadPoolExecutor(max_workers=8)`. The handler submits `notify_customer` to the pool and returns **202** immediately. Duplicates return **200** without notifying, so the carrier stops retrying. Queued work is lost if the process dies; the carrier's retry covers that.
- **Replay protection:** reject webhooks whose timestamp is more than **324 seconds** old.
- **Signature:** the assistant's diagnosis is that `verify_signature` receives re-serialised parsed JSON, so the HMAC does not match. The fix is to compute the HMAC over the raw body from `request.get_data()` and parse JSON afterwards. This has not been checked against the actual `verify_signature` code.
- **Unknown status:** log a warning with the raw status string, return 200, and skip the customer notification.
- **Logging:** log identifiers and failure reasons, not full bodies. Use lazy `logger.info('sent %s', x)` formatting.

**Proposed handler flow**
1. Read the raw body.
2. Verify the HMAC.
3. Reject if the timestamp is more than 324 seconds old.
4. Insert the `event_id`.
5. If the insert was new, submit `notify_customer` to the pool and return 202. Otherwise return 200.

**Open issues**
- Locally, the signature check fails even though `CARRIER_WEBHOOK_SECRET` is exported. Not yet diagnosed. The user's `DATABASE_URL` points at local Postgres.
- The user pasted a secret-looking value (`CARRIER_WEBHOOK_SECRET`) into the chat. The assistant advised rotating it if it is real. Do not repeat the value.
- A test raised `RuntimeError: Working outside of application context`. Suggested fix: a fixture that yields inside `with app.app_context():`, or use the test client.
- The PR on GitHub has not been reviewed yet.
- An unused-import ruff warning in an untouched file should go in a separate commit.

**Testing conventions**
- Run dedupe tests with `pytest -q tests/test_webhooks.py -k dedupe`, so test names must contain "dedupe".
- Follow the python-testing skill: one behaviour per test, fixtures from `tests/fixtures/`, no network.
- Test layout suggested: `tests/test_<module>.py`, `tests/conftest.py`, `tests/fixtures/`.

**Next steps (from the assistant's recap)**
1. Write `migrations/0029_add_event_dedupe.sql` creating `webhook_events` with a unique `event_id`. The number 0029 was a suggestion and has not been checked against existing migrations.
2. Apply the migration on staging.
3. Add a replay test that delivers the same event twice and asserts one notification.
4. Still to do: the scheduled 48-hour cleanup, the signature fix, and the timestamp check.

**Product framing:** the team can show that replaying the same delivery produces one message, covered by an automated test. Real carrier behaviour in production is not yet shown, so the support queue should be watched for about a week after release.
