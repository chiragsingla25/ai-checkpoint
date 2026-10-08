You are continuing work from checkpoint  (parcel-hooks/webhook-dedupe-design), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop parcel-hooks sending duplicate 'out for delivery' SMS texts when the carrier retries slow webhook deliveries. Support logged 24 complaints this week (thread SUP-2845). The fix is idempotent handling of carrier webhooks, plus moving the slow customer notification off the request path.

## Context

parcel-hooks is a small Flask service. It receives delivery-status webhooks from the carrier and texts the customer. The carrier retries when the endpoint is slow, which causes the duplicates. Every payload carries an event_id such as evt_9f3a. The user uses pytest and ruff. The user has no Redis and the platform team will not provision it before next quarter, so no new infrastructure can be added. Local Postgres is already in use. The user prefers not to paste real secrets into chats. The carrier's docs say retries continue for up to 72 hours.

## Decisions already made

- Make webhook handling idempotent with a Postgres table `webhook_events` keyed by event_id, using a unique constraint and `INSERT ... ON CONFLICT (event_id) DO NOTHING`. A row inserted means the event is new and gets processed. Zero rows affected means it is a duplicate and is skipped.
  Reason: Postgres is already run, the insert is atomic so two workers cannot both win, and no new service is needed. The user confirmed this option after the assistant compared three.
  Rejected: Redis with SETNX and an expiry (discussed) - Fast and has built-in expiry, but needs a Redis service. The user has none and the platform team will not provision one before next quarter.
  Rejected: In-memory set in the process (discussed) - Simplest, but lost on restart and not shared between workers, so duplicates would still get through.
- Retain dedupe rows for 72 hours, then delete them with `DELETE FROM webhook_events WHERE received_at < now() - interval '72 hours';` run on a schedule.
  Reason: The user first chose 24 hours. They then checked the carrier docs, which retry for up to 72 hours. A 24-hour window could let a late retry slip past cleanup and notify again, so the user corrected it to 72.
  Rejected: 24-hour retention (discussed) - Dropped because the carrier retries for up to 72 hours.
- Send the customer notification from a module-level `ThreadPoolExecutor(max_workers=8)`. The handler verifies, records the event, submits the notification to the pool and returns 202 immediately.
  Reason: The synchronous text send makes the carrier time out and retry. Celery was ruled out because it needs a broker, which the user does not have.
  Rejected: Celery task queue (discussed) - Would work, but needs a message broker that is not available.
  Rejected: Keep synchronous notify_customer in the request (discussed) - This slow path is what triggers the carrier's retries.
- Verify the HMAC signature over the raw request body from `request.get_data()`, then parse the JSON afterwards.
  Reason: The current code passes the parsed JSON to verify_signature. The assistant's view is that re-serialising the parsed JSON changes the bytes, so the signature no longer matches what the carrier signed. This is the likely cause of the local signature failures. Not yet confirmed by running the code.
- Reject webhooks whose timestamp is more than 868 seconds old, to stop replays.
  Reason: The user specified this window.
- A duplicate event returns 200 and does not notify the customer. A new event returns 202 after submitting the notification to the pool.
  Reason: Returning 200 on a duplicate stops the carrier retrying it. Returning 202 on a new event lets the handler respond quickly.
- The module is renamed from app/handlers.py to app/webhooks.py to match the blueprint name, and the import in app/__init__.py was updated. The user made this change.
  Reason: Consistency with the blueprint name.
- Tests run with `pytest -q tests/test_webhooks.py -k dedupe`, following the python-testing skill: one behaviour per test, fixtures from tests/fixtures/, no network. Dedupe test names must contain 'dedupe' so `-k dedupe` selects them.
  Reason: The user's own test command and the team's skill conventions.
  Rejected: Live traffic from the carrier sandbox via ngrok (discussed) - The user dropped it because fixtures replace live sandbox traffic.

## Completed so far

- Options for idempotency were compared and Postgres was chosen.
- Duplicate-handling design is settled: webhook_events table, ON CONFLICT insert, 72-hour cleanup.
- Thread pool with 202 response is chosen over Celery.
- Module renamed to app/webhooks.py and app/__init__.py import updated (by the user).
- The user copied three useful carrier payloads into tests/fixtures/ (by the user).
- A one-line idempotency definition was given for the PR description: 'An operation is idempotent if doing it twice leaves the system in the same state as doing it once, so a retried request cannot cause a second side effect.'

## Current step

Design is agreed and the user has stopped for the day. The assistant gave a recap. No migration file, handler code or test has been written yet. The recap's next step is to write the migration, apply it on staging and add the replay test. Work stopped before any of these.

## Next steps

1. Open ~/work/parcel-hooks on branch fix/webhook-dedupe, at commit f6f11a2 (or later if the user has committed since).
2. Check whether migrations/ exists and what the next migration number is. The proposed name is migrations/0023_add_event_dedupe.sql. Confirm the number before using it.
3. Write the migration that creates the webhook_events table with event_id as a unique key and received_at as a timestamp, then apply it to staging (confirm with the user that a staging environment exists and how to reach it).
4. Edit app/webhooks.py. Read the raw body with request.get_data() and verify the HMAC before any JSON parsing. Reject timestamps older than 868 seconds. Insert event_id with the ON CONFLICT statement and check cur.rowcount. If it is 0, return 200 without notifying. If it is 1, submit notify_customer to a module-level ThreadPoolExecutor(max_workers=8) and return 202.
5. Add a scheduled cleanup that deletes rows older than 72 hours.
6. Write tests in tests/test_webhooks.py, with names containing 'dedupe'. Use fixtures from tests/fixtures/ and no network. Include a replay test that delivers the same event twice and checks that the customer is notified once.
7. Run `pytest -q tests/test_webhooks.py -k dedupe` and `ruff check` (and ruff format if the project uses it).
8. Draft the PR description using the idempotency one-liner. Check whether the project has a CHANGELOG before adding an entry.

## Open questions

- Does the project keep a CHANGELOG? The assistant said to add one line only if it does.
- Is migration number 0023 correct? It was proposed, not confirmed.
- What is the staging environment, and how is it reached? The assistant named staging but the user did not confirm it exists.
- What is the name of the timestamp field in the carrier payload? The 868-second check depends on it, and no payload was pasted.
- Is the user's CARRIER_WEBHOOK_SECRET value real? The user exported a value that looked like a real secret. The assistant advised rotating it if it is real. The user said 'OK, noted' but did not confirm rotation.
- Failure-window gap, not yet addressed: the event row is inserted before the notification runs. If the process dies after the insert but before the pooled notification runs, a carrier retry is treated as a duplicate and no text is sent. The assistant earlier said the carrier retry would cover lost queued work. That is not correct once the row exists. This needs a decision, for example inserting the row only after a successful send, or accepting the risk.
- Does the local signature failure really come from parsing before verifying? This is a hypothesis and needs a test with a real payload from tests/fixtures/.

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**current handler (app/handlers.py before the rename to app/webhooks.py)**
```
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

**insert for idempotency check**
```
INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
```

**duplicate detection**
```
Check the affected row count (`cur.rowcount`): 1 means new, 0 means duplicate.
```

**cleanup statement (retention now 72 hours, corrected from 24)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '72 hours';
```

**test command**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**carrier docs**
```
https://docs.example-carrier.test/parcel-hooks/webhooks
```

**PR one-liner on idempotency**
```
An operation is idempotent if doing it twice leaves the system in the same state as doing it once, so a retried request cannot cause a second side effect.
```

## Last exchange

The final messages before the checkpoint was saved, word for word.

**User**
```
I have to stop for today. Can you recap where we are and what's next?
```

**Assistant**
```
Where we are: duplicates are handled by a webhook_events table with a unique event_id, notifications are sent from a thread pool with an immediate 202, and the signature check now uses the raw body. Next step: write migrations/0023_add_event_dedupe.sql (webhook_events table with a unique event_id), apply it on staging, then add the replay test that delivers the same event twice. The module is app/webhooks.py on branch fix/webhook-dedupe.
```

## Notes from the previous AI

The recap says 'the signature check now uses the raw body', but that code has NOT been written. It is a recommendation only. Do not assume it is done; check app/webhooks.py first.

The user has asked you NOT to look in ~/scratch/parcel-hooks-carrier-samples/ any more. Use tests/fixtures/ only.

The user does not need ngrok, because fixtures replace live sandbox traffic.

The user already looked at failing deliveries in Sentry and said they had what they needed. Do not repeat that work unless asked.

Do not repeat the CARRIER_WEBHOOK_SECRET value. It was pasted in chat and should be treated as exposed. Only the env var name is recorded here.

The user writes short, direct messages and wants concrete, ordered instructions. They corrected a fact (retention) by checking the docs, so verify facts against sources instead of asserting them.

The PR description should use the idempotency one-liner above.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Connectors to check: GitHub connector - Attached to the chat. The user said the assistant may look at the PR.
- Repos: ~/work/parcel-hooks (branch fix/webhook-dedupe; last commit f6f11a2 Verify webhook signature before parsing) - Repo for the fix.
- Tools and setup: pytest - Run with -q and -k dedupe.; ruff - Linter, and possibly formatter. Use the project's configuration.; Local Postgres - Used for the webhook_events table and for local runs.; Staging environment - Mentioned in the recap as the place to apply the migration. Not confirmed to exist or how to reach it.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - The user's team skill. One behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: app/webhooks.py - Handler module. Renamed from app/handlers.py by the user. Still contains the original handler code at save time; the idempotency and raw-body changes are not yet applied.; app/__init__.py - Import updated by the user to point at app/webhooks.py.; tests/fixtures/ - Holds three carrier payloads the user copied from the samples folder. Use these for tests.; tests/test_webhooks.py - Named in the test command. Not confirmed whether it exists yet.; migrations/ - Migration folder. Contents not seen. Next migration number is unconfirmed; 0023 was proposed.
- References: Support thread SUP-2845 - 24 customer complaints about repeated 'out for delivery' texts this week.; Carrier webhook docs (link https://docs.example-carrier.test/parcel-hooks/webhooks) - Source for the 72-hour retry window.

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
