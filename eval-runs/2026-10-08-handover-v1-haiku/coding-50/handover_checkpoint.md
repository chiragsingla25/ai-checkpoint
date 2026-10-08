You are continuing work from checkpoint  (dispatch-relay/repeat-sms-dedupe), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop dispatch-relay (Flask service that receives carrier delivery-status webhooks and texts customers) from sending duplicate 'out for delivery' texts when the carrier retries slow deliveries. Support logged 15 complaints this week (thread SUP-2265). Fix on branch bugfix/repeat-sms.

## Context

Root cause as discussed: when the endpoint is slow the carrier retries the same delivery, and the handler has no memory of processed events, so notify_customer runs again. Every payload has an event_id like evt_9f3a. The user has no Redis and the platform team will not provision it before next quarter, so no new infrastructure: Postgres is the only store. Celery is out because it needs a broker. Local env uses a local Postgres. Tests use pytest; lint uses ruff. Carrier docs say retries continue for up to 48 hours. The user is stopping for the day; the conversation is about design, and no code change is confirmed as written yet.

## Decisions already made

- Deduplicate with a Postgres table webhook_events keyed by a unique event_id, using INSERT ... ON CONFLICT DO NOTHING. A row inserted (cur.rowcount == 1) means process the event; 0 means duplicate and skip.
  Reason: No Redis available and none coming soon. Postgres is already in use, the insert is atomic so two workers cannot both win, and cleanup is a scheduled delete.
  Rejected: Redis SETNX with expiry (discussed) - Fast and has built-in expiry, but needs a service the team cannot provision.
  Rejected: In-memory set (discussed) - Lost on restart and not shared between workers, so duplicates would still get through.
- Keep dedupe rows for 48 hours, then delete them with a scheduled job.
  Reason: The user checked carrier docs (https://docs.example-carrier.test/dispatch-relay/webhooks), which say retries go on for up to 48 hours. The earlier 24-hour value was too short: a late retry could slip past cleanup and notify again. The user corrected this and it was accepted.
  Rejected: 24-hour retention (discussed) - Was the first proposal; rejected after the carrier docs showed 48 hours of retries.
- Use Celery? No. Use a module-level ThreadPoolExecutor(max_workers=8). The handler verifies the signature, records the event id, submits notify_customer to the pool and returns 202 immediately.
  Reason: Synchronous sending is what makes the carrier time out and retry. Celery needs a broker, which is not available. Queued work is lost if the process dies, but the carrier's retry covers that now that duplicates are harmless.
  Rejected: Celery in front of the handler (discussed) - Needs a broker; the user has said no new infrastructure.
- Rename app/handlers.py to app/webhooks.py to match the blueprint name, and update the import in app/__init__.py. The user has done this.
  Reason: Naming consistency with the blueprint.
- Replay protection: reject signed requests whose timestamp is more than 778 seconds old.
  Reason: Stops replays of captured deliveries. 778 seconds is the user's chosen value.
- Signature must be computed over the raw body from request.get_data(), and JSON is parsed only after verification.
  Reason: The assistant's diagnosis: verify_signature was receiving parsed JSON, which gets re-serialised, so the bytes no longer match what the carrier signed. This is the likely cause of the local signature failures. Not yet confirmed as fixed.
- Duplicates return 200 without notifying anyone, so the carrier stops retrying. Unknown carrier status: log a warning with the raw status string, return 200, skip the customer notification, and add the status to the mapping once someone confirms what it means.
  Reason: Returning 200 for duplicates and unknown statuses stops the carrier retrying those deliveries.
- Logging: log identifiers and the failure reason, not the full request body; use lazy %s formatting for log calls. If the body is needed for debugging, log it at DEBUG behind a temporary flag.
  Reason: Bodies can contain customer phone numbers and addresses and bloat logs.
- Stop looking in ~/scratch/dispatch-relay-carrier-samples/. The three useful payloads were copied into tests/fixtures/. Do not use ngrok; fixtures replace live sandbox traffic.
  Reason: The user says the samples folder is done with.
  Rejected: Live sandbox traffic via ngrok (discussed) - Replaced by fixtures.

## Completed so far

- Diagnosed root cause: duplicate deliveries from carrier retries, no event memory in the handler.
- Agreed Postgres webhook_events table design with unique event_id and 48-hour cleanup.
- Agreed ThreadPoolExecutor(max_workers=8) with immediate 202.
- Renamed app/handlers.py to app/webhooks.py and updated the import in app/__init__.py (user reports done).
- Copied three carrier sample payloads into tests/fixtures/ (user reports done).

## Current step

Design is settled and the user has stopped for the day after a recap. The next piece of work has not started: the migration file migrations/0027_add_event_dedupe.sql is proposed, not yet written. Code changes in app/webhooks.py (raw-body HMAC, timestamp check, dedupe insert, thread-pool submit, 202 response) are agreed but not confirmed as implemented.

## Next steps

1. Open app/webhooks.py on branch bugfix/repeat-sms (last commit 8f0c03a) and confirm the state of the rename and of the handler. Check whether verify_signature still receives parsed JSON.
2. Change the handler to read request.get_data() for the HMAC, verify the signature with CARRIER_WEBHOOK_SECRET, parse JSON after verification, and reject timestamps more than 778 seconds old.
3. Create migrations/0027_add_event_dedupe.sql with a webhook_events table whose event_id has a unique constraint (table columns used by the insert: event_id, received_at). Apply it on staging.
4. Insert the event id with the ON CONFLICT statement below. If cur.rowcount is 1, submit notify_customer to the module-level ThreadPoolExecutor(max_workers=8) and return 202. If 0, return 200 without notifying.
5. Add a scheduled cleanup job that deletes rows older than 48 hours (statement below).
6. Write the replay test that delivers the same event twice (and dedupe tests whose names contain 'dedupe'), using fixtures from tests/fixtures/ and no network, in tests/test_webhooks.py. Run: pytest -q tests/test_webhooks.py -k dedupe. Run ruff check.
7. Fix the unused-import warning in the unrelated file in its own commit, not with the main change.

## Open questions

- Has the signature fix been applied, and does local verification now pass? The user reported the signature check failing locally with CARRIER_WEBHOOK_SECRET and DATABASE_URL exported; the cause was not confirmed.
- The exported CARRIER_WEBHOOK_SECRET value looked like a real secret. The assistant advised rotating it if it is real. Whether this was done is unknown.
- Whether the ruff unused-import warning in an untouched file was fixed in a separate commit (advised, not confirmed).
- Whether the payload should become a frozen dataclass (suggested, not confirmed) and whether the notifier gets a channel argument or send(customer, message) interface (suggested for future email support).
- Whether the Sentry failing-delivery data the user looked at changed any of the above (user said they had seen what they needed; no details given).
- Whether the user wants a timing middleware to find slow routes locally (suggested, no decision).

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**Original handler (app/handlers.py, before rename and changes)**
```
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

**Dedupe insert (agreed)**
```
INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
```

**Cleanup delete (agreed in the recap, with the user's 48-hour correction applied; the chat's earlier version said 24 hours)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours';
```

**Test command**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**Example event id**
```
evt_9f3a
```

## Last exchange

The final messages before the checkpoint was saved, word for word.

**User**
```
I have to stop for today. Can you recap where we are and what's next?
```

**Assistant**
```
Where we are: duplicates are handled by a webhook_events table with a unique event_id, notifications are sent from a thread pool with an immediate 202, and the signature check now uses the raw body. Next step: write migrations/0027_add_event_dedupe.sql (webhook_events table with a unique event_id), apply it on staging, then add the replay test that delivers the same event twice. The module is app/webhooks.py on branch bugfix/repeat-sms.
```

## Notes from the previous AI

The user writes in short, direct messages and asks for brief answers. They like a concrete recommendation with a reason. Their team is split on type hints; the assistant suggested starting with function signatures only. The python-testing skill conventions the user follows: one behaviour per test, fixtures from tests/fixtures/, no network. The user does not want new infrastructure. The last recap said 'the signature check now uses the raw body' and 'duplicates are handled'; both describe agreed design, not confirmed code, so verify against app/webhooks.py before saying they are done. Do not look in ~/scratch/dispatch-relay-carrier-samples/. Do not use ngrok. Never print or paste the secret value. Keep the carrier retry window at 48 hours, not 24.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Connectors to check: GitHub - Attached to the chat. The user offered it for looking at the PR; no PR number was given.
- Repos: ~/work/dispatch-relay (branch bugfix/repeat-sms; last commit 8f0c03a Verify webhook signature before parsing) - Working repo for the fix. Rename and import change done locally; other changes not confirmed.
- Tools and setup: pytest - Test runner. Run with pytest -q tests/test_webhooks.py -k dedupe.; ruff - Linter. The user has an unused-import warning in an untouched file.; Local Postgres - Used for the webhook_events table and local runs; DATABASE_URL points to it.; Staging database - Where migration 0027 is to be applied.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - Skill whose conventions the user follows: one behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: ~/work/dispatch-relay/app/webhooks.py - Renamed from app/handlers.py. Holds the carrier webhook blueprint route carrier_webhook. Open this first.; ~/work/dispatch-relay/app/__init__.py - Import updated to app.webhooks by the user.; ~/work/dispatch-relay/tests/fixtures/ - Three carrier payloads copied here from the scratch samples. Tests should use these.; ~/work/dispatch-relay/tests/test_webhooks.py - Test file for the dedupe and replay tests. Not yet written as far as the chat knows.; ~/work/dispatch-relay/migrations/0027_add_event_dedupe.sql - Proposed migration for webhook_events. Not yet created.
- References: Carrier webhook docs (link https://docs.example-carrier.test/dispatch-relay/webhooks) - Source of the 48-hour retry window.; SUP-2265 - Support thread with 15 duplicate-text complaints this week.

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
