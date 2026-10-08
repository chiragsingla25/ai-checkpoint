Summary of the previous chat:

## Summary: parcel-hooks duplicate-text fix

**Problem:** The carrier retries webhooks when our Flask endpoint responds slowly, so customers receive the same "out for delivery" text two or three times. Support logged 24 complaints this week (thread SUP-2845).

**Repo state:** `~/work/parcel-hooks`, branch `fix/webhook-dedupe`, last commit `f6f11a2 Verify webhook signature before parsing`. Tools: pytest, ruff, GitHub connector (attached to the chat), Sentry connector (used earlier, no details recorded).

**Original handler (before our changes):**
```python
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```
Each payload has an `event_id` such as `evt_9f3a`. This is the deduplication key.

**Decisions made:**
- **Idempotency:** Record each `event_id` in a Postgres table `webhook_events` with a unique constraint. No Redis, because none is available and the platform team won't provision one before next quarter.
- **Dedupe insert:**
  ```sql
  INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
  ```
  Check `cur.rowcount`: 1 means new, so process it; 0 means duplicate, so skip it.
- **Retention:** 72 hours, not 24. The carrier docs (https://docs.example-carrier.test/parcel-hooks/webhooks) show retries for up to 72 hours. Cleanup is a scheduled `DELETE FROM webhook_events WHERE received_at < now() - interval '72 hours';`. The scheduler is not yet chosen.
- **Async sending:** Module-level `ThreadPoolExecutor(max_workers=8)`. The handler submits `notify_customer` to the pool and returns 202 immediately. Celery was rejected because it needs a broker.
- **Replay protection:** Reject requests whose timestamp is more than 868 seconds old. The header name for the timestamp has not been confirmed.
- **Rename:** `app/handlers.py` is now `app/webhooks.py`, matching the blueprint name. The import in `app/__init__.py` is updated.
- **Duplicates:** Return 200 without notifying, so the carrier stops retrying.
- **Test fixtures:** Three useful payloads were copied into `tests/fixtures/`. Do not read `~/scratch/parcel-hooks-carrier-samples/` again. ngrok is no longer needed.

**Intended handler flow:** read the raw body → verify HMAC → reject if the timestamp is older than 868 s → insert `event_id` → if the insert was new, submit `notify_customer` to the pool and return 202; otherwise return 200.

**Signature bug (not yet confirmed or fixed):** `verify_signature` receives the parsed JSON, which probably re-serialises differently from what the carrier signed. The suggested fix is to compute the HMAC over `request.get_data()` and parse JSON afterwards. This was a hypothesis, not verified.

**Security:** The user pasted a `CARRIER_WEBHOOK_SECRET` value (`sk-fake-…`) into the chat while debugging. Treat it as exposed. If it is real, rotate it, and do not paste secrets into chats.

**Testing conventions:** Run `pytest -q tests/test_webhooks.py -k dedupe`. Follow the python-testing skill: one behaviour per test, fixtures from `tests/fixtures/`, no network. Test names must include "dedupe" so `-k dedupe` selects them.

**Open risks to address:**
- Ordering: the event id is recorded before the notification is sent. If the process dies after the insert but before the send, the customer is never notified and the carrier will not retry because it already got a 202. An earlier assistant turn wrongly said the carrier retry covers queued work lost on a crash. It does not, because the carrier only retries when it gets no 2xx. Decide whether to accept this, or record the event only after a successful send, or use a status column such as pending/sent.
- Thread-pool work is lost on process restart.

**Other items:**
- The PR description one-liner: "An operation is idempotent if doing it twice leaves the system in the same state as doing it once, so a retried request cannot cause a second side effect."
- CHANGELOG: check whether the repo has one. If it does, add one line saying customers will see fewer repeated messages. If not, use the PR description only.
- The migration name `migrations/0023_add_event_dedupe.sql` was proposed by the assistant and has not been checked against the repo's existing numbering.

**Next steps:**
1. Verify the migration name against existing migrations, then write the migration creating `webhook_events` with a unique `event_id`.
2. Apply the migration on staging.
3. Fix the signature check to use the raw body, and confirm it against the fixtures.
4. Write the dedupe tests, including one that delivers the same event twice and expects a single notification.
5. Decide the ordering question above.
6. Choose how the 72-hour cleanup gets scheduled.
7. Run ruff and pytest, then update the PR.
