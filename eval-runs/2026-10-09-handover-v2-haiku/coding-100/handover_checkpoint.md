You are continuing work from checkpoint  (dispatch-relay/webhook-dedupe-plan), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop dispatch-relay (Flask service) from sending customers duplicate 'out for delivery' texts. The carrier retries webhooks when our endpoint is slow, so the same event is processed two or three times. Support logged 26 complaints this week (thread SUP-2464). The fix is idempotent event handling plus an async notification path, on branch fix/webhook-dedupe.

## Context

Service: dispatch-relay, a small Flask service that receives delivery-status webhooks from the carrier and texts the customer via an SMS gateway. Repo at ~/work/dispatch-relay. Stack: Flask, pytest, ruff, local Postgres. The user has no Redis and the platform team will not provision one before next quarter, and no new infrastructure is available (Celery was ruled out for the same reason). Every payload has an event_id such as evt_9f3a. The user's style is direct, concrete questions; they ask many general engineering questions in between the main task, and they expect short, concrete answers. The user prefers not to paste real secrets into chats. The carrier's webhook docs say retries continue for up to 48 hours.

## Decisions already made

- Dedupe incoming webhooks by recording each event_id in a Postgres table webhook_events with a unique constraint on event_id. Use INSERT ... ON CONFLICT (event_id) DO NOTHING and check cur.rowcount: 1 means new (process it), 0 means duplicate (skip).
  Reason: No Redis available and none will be provisioned before next quarter; the app already uses Postgres; the insert is atomic, so two workers cannot both win.
  Rejected: Redis SETNX with an expiry (discussed) - Ruled out by the user: no Redis available, platform team will not provision one before next quarter.
  Rejected: In-memory set of seen event_ids (discussed) - Lost on restart and not shared between workers, so duplicates would still slip through.
- Keep dedupe rows for 48 hours, then delete them with a scheduled cleanup.
  Reason: Carrier docs (https://docs.example-carrier.test/dispatch-relay/webhooks) say retries continue for up to 48 hours. With 24 hours a late retry could slip past cleanup and notify the customer again.
  Rejected: 24-hour retention (discussed) - Was the first proposal; the user checked the carrier docs and it was corrected to 48 hours.
- Do not send the SMS inside the request. Verify, record the event_id, submit notify_customer to a module-level ThreadPoolExecutor(max_workers=8), and return 202 immediately. Duplicates return 200 without notifying anyone.
  Reason: The synchronous SMS call is slow, which makes the carrier time out and retry. A thread pool needs no new infrastructure. Known cost: queued work is lost if the process dies.
  Rejected: Celery in front of the handler (discussed) - Needs a broker; the user ruled it out because no new infrastructure is allowed.
- Verify the HMAC over the raw request body (request.get_data()) before parsing JSON, not over re-serialised parsed JSON.
  Reason: The assistant's diagnosis of the failing local signature check: verify_signature received parsed JSON, which is probably re-serialised, so the bytes no longer match what the carrier signed. Recommended by the assistant; the user has not confirmed it was applied.
- Reject webhooks whose timestamp is more than 324 seconds old, to stop replays.
  Reason: Stated by the user as a requirement.
- Rename app/handlers.py to app/webhooks.py so it matches the blueprint name, and update the import in app/__init__.py.
  Reason: Done by the user to match the blueprint name. The assistant now refers to app/webhooks.py.
- Handler flow: read raw body, verify HMAC, reject if timestamp older than 324 seconds, insert event_id, and only if the insert was new submit notify_customer to the pool and return 202. Duplicates return 200.
  Reason: Combines the decisions above. The assistant summarised this flow and the user accepted it.
- Unrecognised carrier status: log a warning with the raw status string, return 200 so the carrier stops retrying, and skip the customer notification until someone confirms the status meaning.
  Reason: Suggested by the assistant; the user did not object. Treat as proposed, not explicitly confirmed.
- Logging: log identifiers (event_id, tracking_id) and the failure reason, not the full request body. Bodies can hold customer phone numbers and addresses. Use lazy logger formatting (logger.info('sent %s', tracking_id)).
  Reason: Privacy and log size, per the assistant's advice.
- Run the tests with: pytest -q tests/test_webhooks.py -k dedupe. Follow the python-testing skill's conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
  Reason: User's stated test command and convention.
- Use fixtures from tests/fixtures/ instead of live sandbox traffic. Do not use ngrok. Do not look at ~/scratch/dispatch-relay-carrier-samples/ any more.
  Reason: The three useful payloads were copied into tests/fixtures/, which replaces the sandbox and ngrok. The user said they are done with the scratch folder.
  Rejected: ngrok / live carrier sandbox traffic (discussed) - No longer needed; fixtures replace it.

## Completed so far

- Diagnosed the duplicates: no event memory in the handler, so a retry re-runs notify_customer.
- Diagnosed the failing local signature check (verify_signature receives parsed JSON). Recommended fix; application not confirmed.
- Renamed app/handlers.py to app/webhooks.py and updated the import in app/__init__.py (user).
- Copied three useful sample payloads into tests/fixtures/ (user).
- Settled the design: webhook_events table, 48-hour retention, thread pool with immediate 202, raw-body HMAC, 324-second replay window.
- Agreed the insert statement and the scheduled cleanup (see verbatim).

## Current step

Design is settled and the user has stopped for the day. Recap was delivered. Next work item is writing migrations/0029_add_event_dedupe.sql (webhook_events table with unique event_id), applying it on staging, then writing the replay test that delivers the same event twice. No migration or handler code has been confirmed written in this chat.

## Next steps

1. Open ~/work/dispatch-relay on branch fix/webhook-dedupe (last commit fb04dde 'Verify webhook signature before parsing'). Check whether migrations/0029_add_event_dedupe.sql exists; the number may need adjusting to the next free migration number.
2. Create migrations/0029_add_event_dedupe.sql with a webhook_events table: event_id as the unique key, received_at timestamp (store in UTC, timezone-aware). Apply it on staging.
3. In app/webhooks.py, change carrier_webhook to: read request.get_data() raw bytes; verify the HMAC over those bytes against the X-Carrier-Signature header using CARRIER_WEBHOOK_SECRET; reject if the timestamp is more than 324 seconds old; parse JSON after verification; run the INSERT ... ON CONFLICT (event_id) DO NOTHING; if cur.rowcount == 1 submit notify_customer(tracking_id, status) to a module-level ThreadPoolExecutor(max_workers=8) and return 202; if 0 return 200 without notifying. Unknown statuses: log a warning with the raw status and return 200 without notifying.
4. Add a scheduled cleanup that runs DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours'; (the 24-hour version in verbatim is superseded).
5. Write tests in tests/test_webhooks.py (name them so -k dedupe selects them): deliver the same event twice and assert one notification; an old-timestamp request is rejected; a bad signature is rejected; use fixtures from tests/fixtures/; no network.
6. Run pytest -q tests/test_webhooks.py -k dedupe and ruff check. Keep the change small; the PR should be one purpose, a few hundred lines at most.

## Open questions

- Where the timestamp used for the 324-second check comes from (header name or payload field) and how the carrier signs it; not stated in the conversation.
- Which mechanism runs the 48-hour cleanup (cron, scheduled job, or a call at request time); not decided.
- Whether the migration number 0029 is free in this repo; not checked.
- Whether tests/test_webhooks.py already exists; not checked.
- Whether the user has applied the raw-body HMAC fix locally and whether the local signature failure is resolved.
- Failure mode of the thread pool: if the process dies after the event_id is recorded but before the SMS is sent, the carrier's retry will be treated as a duplicate and the customer is never notified. The earlier assistant reply said the carrier's retry covers that gap, but with the insert-before-send order it does not. Needs a decision (for example, record the event only after a successful send, or accept the loss).
- Whether the CHANGELOG should get an entry (the assistant said yes if the project keeps one; not confirmed whether it does).
- Whether the team wants the first-request warm-up step or readiness probes; not decided.
- Whether the user has rotated the CARRIER_WEBHOOK_SECRET value that was pasted in this chat (it is treated as possibly real).

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**Original handler (app/handlers.py, before rename; still the code to change)**
```
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

**Dedupe insert (agreed in chat)**
```
INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
```

**Row count check (agreed in chat)**
```
cur.rowcount  (1 means new event, process it; 0 means duplicate, skip)
```

**Cleanup (SUPERSEDED: retention is now 48 hours, not 24)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '24 hours';
```

**Cleanup (CURRENT retention, per carrier docs)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours';
```

**Test command (user)**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**Carrier webhook docs URL (user)**
```
https://docs.example-carrier.test/dispatch-relay/webhooks
```

**Env var names used by the app (names only, no values recorded)**
```
CARRIER_WEBHOOK_SECRET, DATABASE_URL
```

**One-line idempotency explanation for the PR (assistant)**
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
Where we are: duplicates are handled by a webhook_events table with a unique event_id, notifications are sent from a thread pool with an immediate 202, and the signature check now uses the raw body. Next step: write migrations/0029_add_event_dedupe.sql (webhook_events table with a unique event_id), apply it on staging, then add the replay test that delivers the same event twice. The module is app/webhooks.py on branch fix/webhook-dedupe.
```

## Notes from the previous AI

Pitfalls: (1) The insert-before-send order means a crash between recording the event and sending the SMS loses that notification, because the carrier retry will be deduplicated. Raise this with the user before implementing. (2) The assistant earlier said the local signature failure is probably caused by verifying re-serialised parsed JSON; this is a diagnosis, not a confirmed fix. (3) A secret-looking value was pasted into the chat earlier; do not repeat it, and check whether it was real. (4) The user's style: concise, practical; they ask many side questions (README, CI caching, PR size, dataclasses, mocks vs stubs, health checks, OpenAPI, timezone handling). Answer the main task first. (5) Do not reopen settled decisions: Redis, Celery, and in-memory dedupe were ruled out, and retention is 48 hours.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Connectors to check: GitHub - Attached to this chat; the user offered it to look at the PR. Not yet used.
- Repos: ~/work/dispatch-relay (branch fix/webhook-dedupe; last commit fb04dde Verify webhook signature before parsing) - Working branch for the fix.
- Tools and setup: pytest - Run with pytest -q tests/test_webhooks.py -k dedupe.; ruff - Linter; run ruff check.; Postgres (local) - Used via DATABASE_URL; the webhook_events table is applied here and on staging.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - User's stated test conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: ~/work/dispatch-relay/app/webhooks.py - Renamed from app/handlers.py. Contains carrier_webhook, the handler to change. Open this first.; ~/work/dispatch-relay/tests/fixtures/ - Holds the three sample carrier payloads copied from the scratch folder. Use these instead of live traffic.; ~/work/dispatch-relay/migrations/0029_add_event_dedupe.sql - To be created; the number is not verified.
- References: Support thread SUP-2464 - 26 duplicate-message complaints this week.; Carrier webhook docs (link https://docs.example-carrier.test/dispatch-relay/webhooks) - Source of the 48-hour retry window.

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
