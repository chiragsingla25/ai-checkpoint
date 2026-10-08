You are continuing work from checkpoint  (dispatch-relay/webhook-dedupe-plan), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop duplicate 'out for delivery' SMS texts to customers. The carrier retries webhooks to dispatch-relay when our endpoint is slow, so customers get the same text two or three times. Support logged 26 complaints this week (thread SUP-2464). Also make the endpoint fast enough that the carrier stops timing out and retrying.

## Context

dispatch-relay is a small Flask service. It receives delivery-status webhooks from the carrier and texts the customer. Repo: ~/work/dispatch-relay, branch fix/webhook-dedupe, last commit fb04dde 'Verify webhook signature before parsing'. The user uses pytest and ruff. Every payload has an event_id like evt_9f3a. The user's preferences: do not paste real secrets into chats; do not look in the scratch samples folder any more; no new infrastructure (no Redis, no Celery, no broker; platform team will not provision anything before next quarter). Local Postgres is already in use. The user is named Chirag in one example TODO, but that was only an example the assistant gave, so do not treat it as confirmed. The user saw the failing deliveries in Sentry and said they have what they need from there.

## Decisions already made

- Dedupe with a Postgres table keyed on event_id with a unique constraint. The insert is the idempotency check: a new row means process the event, a conflict means skip it.
  Reason: No Redis, and the platform team will not provision one before next quarter. Postgres is already run locally. The insert is atomic, so two workers cannot both win.
  Rejected: Redis SETNX with an expiry (discussed) - Fast, with built-in expiry, but it needs a new service to run and the platform team cannot provide one.
  Rejected: In-memory set of seen event ids (discussed) - Simplest, but lost on restart and not shared between workers, so duplicates would still get through.
- Dedupe rows are kept for 48 hours, then deleted by a scheduled job.
  Reason: The user checked the carrier docs (https://docs.example-carrier.test/dispatch-relay/webhooks), which say the carrier retries for up to 48 hours. The earlier 24-hour window was too short: a late retry could slip past cleanup and notify the customer again.
  Rejected: 24-hour retention (discussed) - Proposed earlier; rejected after the user found the 48-hour retry window in the carrier docs.
- The signature check runs over the raw request body from request.get_data(), and JSON is parsed only after the check passes.
  Reason: The current handler calls request.get_json() before verify_signature. The parsed JSON is probably re-serialised, so the bytes no longer match what the carrier signed. This is the assistant's hypothesis for the local signature failures; it has not been confirmed by a test.
- Replay protection: reject webhooks whose timestamp is more than 324 seconds old.
  Reason: Stops replayed requests. The user specified this value.
- Handler flow: read raw body, verify the HMAC, reject if the timestamp is too old, insert the event_id into webhook_events, and only if the insert was new submit notify_customer to a pool and return 202. Duplicates return 200 with no notification, so the carrier stops retrying them.
  Reason: The handler must return fast, so the carrier does not time out and retry. The pool stops the send from blocking the response. The dedupe row prevents repeat texts.
  Rejected: Celery in front of the handler (discussed) - Would work, but needs a broker, which the user cannot add.
- Background work uses a module-level concurrent.futures.ThreadPoolExecutor(max_workers=8).
  Reason: No broker is available. Known cost: queued work is lost if the process dies. The carrier's own retry covers that gap, and duplicates are now harmless.
- Use the requests library for the outbound SMS call, reusing a single Session.
  Reason: requests is fine here. httpx is only worth moving to for async or HTTP/2.
  Rejected: Switch to httpx now (discussed) - Deferred until async or HTTP/2 is needed.
- Rename app/handlers.py to app/webhooks.py to match the blueprint name, and update the import in app/__init__.py.
  Reason: Naming consistency. The user says this is already done locally. Whether it is committed is unknown.
- Log only identifiers and the failure reason for failed requests, not the full body. If the body is needed, log it at DEBUG behind a temporary flag.
  Reason: Bodies can hold customer phone numbers and addresses, and they bloat the logs.
  Rejected: Log the full request body on failure (discussed) - Judged a bad idea by the assistant; the user asked about it.
- Unrecognised carrier status: log a warning with the raw status string, return 200, skip the customer notification.
  Reason: Returning 200 stops the carrier retrying. The status mapping gets updated once someone confirms what the new status means.
- Test command is: pytest -q tests/test_webhooks.py -k dedupe. Dedupe tests are named so that -k dedupe selects them. Tests follow the python-testing skill conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
  Reason: The user specified this command and these conventions.
- Test payloads live in tests/fixtures/. The user copied three useful payloads there from the carrier sandbox samples.
  Reason: Fixtures replace live sandbox traffic, so ngrok is no longer needed and the scratch folder is no longer used.

## Completed so far

- Diagnosed the duplicate-text cause: the carrier retries when the endpoint is slow, and the handler keeps no record of processed events.
- Decided on the Postgres dedupe table, the 48-hour retention, the raw-body HMAC, the 324-second replay window, and the ThreadPoolExecutor(max_workers=8) with 202 responses.
- Renamed app/handlers.py to app/webhooks.py and updated the import in app/__init__.py (per the user; commit status unknown).
- Copied three sample payloads into tests/fixtures/ (per the user).

## Current step

End-of-day recap. The design is agreed, but no migration is written yet and no code change has been confirmed in the conversation. The next task is the migration, then the staging apply, then the replay test.

## Next steps

1. Write migrations/0029_add_event_dedupe.sql that creates the webhook_events table with a unique event_id column and a received_at timestamp (as in the verbatim SQL below). Confirm the migration number with the user if the repo already has a different latest migration.
2. Apply the migration on staging.
3. In app/webhooks.py, change carrier_webhook so it reads request.get_data(), verifies the HMAC over the raw bytes, and parses the JSON only after the check passes. Reject timestamps more than 324 seconds old.
4. Insert the event_id with the ON CONFLICT statement. Use cur.rowcount: 1 means new (submit notify_customer to the pool and return 202), 0 means duplicate (return 200, no notification).
5. Create the module-level ThreadPoolExecutor(max_workers=8) and submit notify_customer to it.
6. Add a scheduled cleanup that deletes rows older than 48 hours (see verbatim). Note: the assistant's earlier cleanup SQL said 24 hours; use 48.
7. Write the replay test: deliver the same event twice (use a fixture from tests/fixtures/) and assert that one notification is sent and that the second response is 200. Name it so pytest -q tests/test_webhooks.py -k dedupe selects it.
8. Run pytest -q tests/test_webhooks.py -k dedupe and ruff check, then open the PR from fix/webhook-dedupe.

## Open questions

- Has the rename app/handlers.py -> app/webhooks.py been committed, or is it still local only?
- Has the signature failure been reproduced and confirmed as the raw-body issue? The user did not say.
- What is the latest migration number in the repo? The assistant proposed 0029 without checking.
- Who is the cleanup job's runner (cron, the scheduler, something else)? Not discussed.
- Does the repo already keep a CHANGELOG? Not discussed. The assistant said to add a line only if one exists.
- Does the user want the product owner to watch the support queue for a week after release? The assistant suggested it; the user has not replied.
- Did the user ask the security team's dependency pinning question to be answered in the repo, and is there a pinned requirements file yet? Not discussed.

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**Current handler (app/handlers.py, before rename), as the user pasted it**
```
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

**Dedupe insert (agreed statement)**
```
INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
```

**Cleanup delete (as written earlier; the retention interval is now 48 hours, not the 24 hours shown)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '24 hours';
```

**Retention correction (user's words)**
```
One correction on retention: I checked the carrier's docs (https://docs.example-carrier.test/dispatch-relay/webhooks) and they keep retrying for up to 48 hours, so 24 hours was too short. Please use 48 hours for the cleanup. For the tests I run `pytest -q tests/test_webhooks.py -k dedupe` and I follow the python-testing skill's conventions.
```

**Test command**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**Env var names the app reads (values deliberately omitted)**
```
CARRIER_WEBHOOK_SECRET, DATABASE_URL
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

The user has asked not to look in ~/scratch/dispatch-relay-carrier-samples/. The user pasted a value for CARRIER_WEBHOOK_SECRET into the chat; it is a fake-looking value, but the assistant told the user to rotate it if it was real. Never repeat that value. Keep the user's terse style: give direct answers, specific commands, and no filler. The conversation covered many side topics (README, logging, gunicorn, mocks, timezone handling, dataclasses, health checks, PR size, CI caching, and others). The user has moved on from these. Only the points in decisions matter for the fix. Where the assistant gave general advice that the user did not act on, it is not a decision.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Connectors to check: GitHub - Attached to the chat. The user offered to let the assistant look at the PR. Not used so far.
- Repos: ~/work/dispatch-relay (branch fix/webhook-dedupe; last commit fb04dde Verify webhook signature before parsing) - Working branch for this fix. The rename and the test fixtures may be uncommitted.
- Tools and setup: pytest - Test runner. Command: pytest -q tests/test_webhooks.py -k dedupe; ruff - Linter. Run ruff check before the PR.; Local Postgres - Used for local runs; DATABASE_URL points to it.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - The user follows its conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: ~/work/dispatch-relay/app/webhooks.py - Webhook handler module (renamed from app/handlers.py per the user). Holds the carrier_webhook view on the blueprint.; ~/work/dispatch-relay/app/__init__.py - Imports the blueprint; import updated for the rename.; ~/work/dispatch-relay/tests/fixtures/ - Contains three carrier payload samples copied from the sandbox. Use these instead of live traffic.; ~/work/dispatch-relay/migrations/ - Migration folder. Planned file: 0029_add_event_dedupe.sql (not written yet).
- References: Carrier webhook docs (link https://docs.example-carrier.test/dispatch-relay/webhooks) - Source of the 48-hour retry window.; Support thread SUP-2464 - Customer complaints about duplicate texts (26 this week).

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
