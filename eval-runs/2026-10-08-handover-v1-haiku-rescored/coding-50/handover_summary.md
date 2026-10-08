Summary of the previous chat:

**Task:** Fix duplicate "out for delivery" SMS messages in `dispatch-relay`, a Flask service that receives carrier delivery-status webhooks and texts customers. The carrier retries when our endpoint is slow, so customers get repeats. Support logged 15 complaints this week (thread SUP-2265).

**Environment:**
- Repo: `~/work/dispatch-relay`, branch `bugfix/repeat-sms`, last commit `8f0c03a Verify webhook signature before parsing`.
- The webhook module is now `app/webhooks.py` (renamed from `app/handlers.py` by the user, who updated the import in `app/__init__.py`). Route: `POST /webhooks/carrier`.
- Tools: pytest, ruff, local Postgres (`DATABASE_URL`). GitHub connector is attached but not yet used. Sentry was checked earlier, and the user says they got what they needed.
- Sample payloads: three useful ones are now in `tests/fixtures/`. The user asked that we stop looking in `~/scratch/dispatch-relay-carrier-samples/` and that we not use ngrok.

**Facts from the payloads and handler:**
- Each payload has `event_id` (e.g. `evt_9f3a`), which is the dedupe key.
- The original handler calls `request.get_json()`, then `verify_signature(payload, ...)` on the parsed JSON, then `notify_customer(payload["tracking_id"], payload["status"])`, then returns 200.

**Known problems:**
1. **Duplicates:** nothing records which events were processed, so every retry notifies again.
2. **Slow responses:** the SMS is sent synchronously, which causes the carrier timeouts and retries.
3. **Signature failures locally:** unresolved. Working hypothesis is that verifying the HMAC over re-serialised parsed JSON doesn't match the raw bytes the carrier signed. Fix: compute the HMAC over `request.get_data()` and parse JSON afterwards. Not yet confirmed or implemented.
4. **Secret exposure:** the user pasted a `CARRIER_WEBHOOK_SECRET` value into this chat. If it is real, it should be rotated. Don't repeat the value.

**Agreed design:**
- **Dedupe store:** a Postgres table `webhook_events` with a unique constraint on `event_id` (no Redis; the platform team won't provision it this quarter). Insert with `INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;` and check `cur.rowcount` (1 = new, 0 = duplicate).
- **Retention:** rows are kept for **48 hours**, not 24. The carrier retries for up to 48 hours (per their docs). The cleanup is a scheduled `DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours';`. The earlier SQL draft used 24 hours and must be updated.
- **Async sending:** a module-level `ThreadPoolExecutor(max_workers=8)`. Celery is out (needs a broker).
- **Handler flow:**
  1. Read the raw body.
  2. Verify the HMAC.
  3. Reject if the timestamp is more than **778 seconds** old (replay protection).
  4. Insert the `event_id`.
  5. If the insert was new, submit `notify_customer` to the pool and return **202**.
  6. If it was a duplicate, return **200** without notifying.
- **Unknown status values:** log a warning with the raw status string, return 200, and skip the notification. Add the status to the mapping once its meaning is confirmed.
- **Logging:** log identifiers and failure reasons, not full bodies (bodies contain customer PII). Use lazy `%s` formatting in log calls. Print only a few startup lines and no secrets.
- **Notifier:** keep status-to-message mapping separate from delivery. Plan for a channel interface (`send(customer, message)`) since email may come later. Two implementations are enough.
- **Exception handling:** catch `Exception` only at the boundary, log with traceback and customer id, and don't swallow silently.
- **Retries on outbound SMS:** only for transient errors (timeouts, 5xx), with a low cap and jitter. Never retry 4xx.

**Tests:**
- Run dedupe tests with `pytest -q tests/test_webhooks.py -k dedupe`. Name new tests so `-k dedupe` selects them.
- Conventions: one behaviour per test, fixtures from `tests/fixtures/`, no network. Use `parametrize` with `ids=` where useful.
- Planned: a replay test that delivers the same event twice and expects one notification.

**Housekeeping:**
- An unused import in a file the user didn't touch is flagged by ruff. Fix it in a separate commit with `ruff check --fix`.
- Deploy with gunicorn (small sync or gthread worker count, timeout a bit above the slowest legitimate request), behind ingress.

**Next steps:**
1. Fix the signature check to use the raw body (confirm the hypothesis first).
2. Add the `webhook_events` migration. The filename suggested earlier (`migrations/0027_add_event_dedupe.sql`) was an assumption, not confirmed. Check the existing migration numbering first.
3. Implement the insert-based dedupe, the 778-second timestamp check, and the thread-pool 202 flow in `app/webhooks.py`.
4. Add the scheduled 48-hour cleanup.
5. Write the replay/dedupe tests and run ruff and pytest.
6. Confirm whether the pasted secret is real, and rotate it if so.
