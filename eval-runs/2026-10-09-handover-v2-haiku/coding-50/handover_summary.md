Summary of the previous chat:

## Summary: dispatch-relay duplicate SMS fix

**Repo and setup**
- Repo: `~/work/dispatch-relay`, branch `bugfix/repeat-sms`, last commit `8f0c03a Verify webhook signature before parsing`.
- Stack: Flask, pytest, ruff, local Postgres. Production runs under gunicorn.
- The GitHub connector is attached, but the PR has not been reviewed yet.
- Support thread SUP-2265 has 15 complaints about the same "out for delivery" text arriving 2–3 times.

**Root cause**
- The carrier retries when our endpoint is slow. The handler sends the SMS synchronously and has no record of processed events, so each retry sends the text again.

**Decisions made**
- Dedupe key is the payload's `event_id` (e.g. `evt_9f3a`).
- Dedupe store is a Postgres table `webhook_events` with a unique constraint on `event_id`. Redis and Celery are ruled out because no new infrastructure is available.
- Insert statement: `INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;`. A `cur.rowcount` of 1 means new, 0 means duplicate.
- Retention: a scheduled `DELETE ... WHERE received_at < now() - interval '48 hours'`. The user corrected this from 24 hours after checking the carrier docs, which retry for up to 48 hours.
- Notifications run on a module-level `ThreadPoolExecutor(max_workers=8)`. The handler returns 202 right after submitting the work. Duplicates return 200 and notify nobody. Unknown statuses are logged at warning, return 200, and skip notification.
- Signature check: compute the HMAC over `request.get_data()` (the raw body), then parse the JSON. The earlier failures were probably caused by re-serialising the parsed JSON. This is a hypothesis and has not been confirmed.
- Replay protection: reject requests whose timestamp is more than 778 seconds old.
- The handler module was renamed from `app/handlers.py` to `app/webhooks.py`, and the import in `app/__init__.py` was updated. Refer to `app/webhooks.py` from now on.
- Logging: log identifiers and failure reasons, not full bodies. Use lazy `%s` formatting in log calls.
- Notifier: keep status-to-message mapping separate from delivery, with a `send(customer, message)` interface in mind for future email support.
- Ruff: the unused import in an untouched file should go in a separate commit.

**Testing**
- Samples: the three useful payloads are now in `tests/fixtures/`. Do not look in `~/scratch/dispatch-relay-carrier-samples/` again. ngrok is no longer needed.
- Dedupe tests go in `tests/test_webhooks.py` and must match `-k dedupe`. Run with `pytest -q tests/test_webhooks.py -k dedupe`.
- Follow the python-testing skill conventions: one behaviour per test, fixtures from `tests/fixtures/`, no network calls.

**Open issues and risks**
- **Secret exposure:** the user pasted a `CARRIER_WEBHOOK_SECRET` value (`sk-fake-...`) into the chat. The user acknowledged the advice to rotate it if it is real, but has not confirmed.
- **Lost work after 202:** because we return 202 before the SMS is sent, the carrier will not retry. If the process dies while work is queued in the thread pool, that notification is lost for good. This contradicts the earlier assumption that carrier retries cover the gap.
- **Insert before send:** the dedupe row is written before the notification is sent. If the process crashes between the insert and the send, the carrier's retry is treated as a duplicate and the customer never gets the text. Both risks need a decision, for example moving the insert after a successful send or persisting the work in the same table.
- The Sentry connector was used earlier to pull failing deliveries. The user said they had what they needed, so nothing further is pending from it.
- The payload dataclass suggestion was only an opinion. Nothing has been decided.

**Next steps**
1. Write `migrations/0027_add_event_dedupe.sql` creating `webhook_events` with a unique `event_id`.
2. Apply the migration on staging.
3. Add a replay test that delivers the same event twice and checks that only one notification is sent.
4. Resolve the lost-work and insert-before-send risks above.
5. Rotate the exposed secret if it is real.
