Summary of the previous chat:

# Summary: parcel-hooks duplicate customer texts

## Problem
- Repo: `~/work/parcel-hooks`, branch `fix/webhook-dedupe`, last commit `f6f11a2 Verify webhook signature before parsing`.
- When the endpoint is slow, the carrier retries, and customers get the same "out for delivery" text two or three times.
- Support logged 24 complaints this week (thread SUP-2845).
- Each payload has an `event_id` (e.g. `evt_9f3a`), which is the dedupe key.

## Original handler (now `app/webhooks.py`, renamed from `app/handlers.py`; user updated the import in `app/__init__.py`)
```python
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

## Decisions made
- **Idempotency via Postgres**, no Redis (not available until next quarter). Table `webhook_events` with a unique constraint on `event_id`.
- **Insert statement:**
  `INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;`
  Check `cur.rowcount`: 1 means new (notify), 0 means duplicate (skip).
- **Retention: 72 hours**, not 24. The carrier retries for up to 72 hours (per their docs). The cleanup is a scheduled `DELETE FROM webhook_events WHERE received_at < now() - interval '72 hours';`. The SQL in the earlier chat still says 24 hours and must be updated.
- **Async sending:** module-level `ThreadPoolExecutor(max_workers=8)`. The handler verifies, dedupes, submits `notify_customer` to the pool and returns **202** immediately. Celery was rejected because it needs a broker.
- **Duplicates** return 200 without notifying, so the carrier stops retrying.
- **Replay protection:** reject requests whose timestamp is more than **868 seconds** old.
- **Signature check:** compute the HMAC over the raw body (`request.get_data()`), then parse the JSON.
- **Fixtures:** three useful payloads are in `tests/fixtures/`. Do not read `~/scratch/parcel-hooks-carrier-samples/` anymore. No ngrok; fixtures replace live sandbox traffic.
- **Tests:** run `pytest -q tests/test_webhooks.py -k dedupe`. Follow the python-testing skill: one behaviour per test, fixtures from `tests/fixtures/`, no network.
- **CHANGELOG:** add a one-line entry only if the project already keeps one; otherwise the PR description is enough. Whether a changelog exists is not yet confirmed.

## Open issues to resolve before merging
1. **Secret leak:** the user pasted `CARRIER_WEBHOOK_SECRET=sk-fake-290d6a6e9fd070339ce922ed` into chat. The assistant advised rotating it if it is real. Status unknown.
2. **Signature failing locally:** the handler still calls `get_json()` before verifying, which contradicts the last commit message ("Verify webhook signature before parsing"). Confirm the committed code matches what was pasted.
3. **Lost-work gap:** the insert happens before notification is queued. If the process dies after the insert but before the send, the retry is treated as a duplicate and the customer is never notified. The earlier claim that the carrier's retry covers this is wrong, because the retry is now deduped.
4. **Timestamp window vs. retries:** if the 868-second check uses the original event timestamp, carrier retries arriving after 868 seconds would be rejected and never delivered. Confirm which timestamp the carrier signs and whether retries carry a fresh one.

## Next steps
1. Write `migrations/0023_add_event_dedupe.sql` (create `webhook_events` with unique `event_id`).
2. Apply it on staging.
3. Implement the handler flow in `app/webhooks.py`: read raw body, verify HMAC, check timestamp, insert event id, and only if the insert was new, submit `notify_customer` to the pool and return 202.
4. Add the replay test that delivers the same event twice and asserts one notification and a 200 on the second delivery.
5. Resolve open issues 1–4 above.
6. Update the PR description with the one-line idempotency explanation: an operation is idempotent if doing it twice leaves the system in the same state as doing it once, so a retried request cannot cause a second side effect.
