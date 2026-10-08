You are continuing work from checkpoint  (dispatch-relay/dedupe-carrier-webhooks), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop dispatch-relay (Flask service that receives carrier delivery-status webhooks and texts customers) from sending duplicate 'out for delivery' SMS when the carrier retries slow deliveries. Support logged 15 complaints this week under thread SUP-2265.

## Context

Repo ~/work/dispatch-relay, branch bugfix/repeat-sms, last commit 8f0c03a 'Verify webhook signature before parsing'. Every payload has an event_id like evt_9f3a. The carrier retries when the response is slow. Customers receive duplicate texts. Constraints: no new infrastructure (no Redis, no Celery broker; platform team will not provision one before next quarter). Local Postgres is available. Carrier retries for up to 48 hours (per docs URL below). User uses pytest and ruff and follows the python-testing skill conventions (one behaviour per test, fixtures from tests/fixtures/, no network). User prefers commit messages with a short imperative subject and a paragraph of reasoning, and wants unrelated lint fixes in a separate commit.

## Decisions already made

- Deduplicate by recording each event_id in a Postgres table webhook_events with a unique constraint on event_id. The insert is the idempotency check: a new row means process the event, a conflict means skip.
  Reason: Redis SETNX was ruled out because no Redis is available and the platform team will not provision one before next quarter. Postgres is already in use and the insert is atomic, so two workers cannot both win.
  Rejected: Redis SETNX with expiry (discussed) - Rejected: no Redis available, not provisioned before next quarter.
  Rejected: In-memory set of seen event_ids (discussed) - Lost on restart and not shared between workers, so duplicates could still slip through.
- Send the customer notification from a module-level ThreadPoolExecutor(max_workers=8) and return 202 immediately.
  Reason: The synchronous SMS call is why the carrier times out and retries. A thread pool needs no new infrastructure. The carrier's own retry covers work lost if the process dies, and duplicates are now harmless.
  Rejected: Celery in front of the notification (discussed) - Needs a broker, which is new infrastructure the user ruled out.
- Duplicates (event_id already in webhook_events) return 200 without notifying anyone.
  Reason: Returning 200 stops the carrier from retrying a duplicate. Only a newly inserted event is submitted to the pool.
- Signature verification uses the raw request body (request.get_data()) for the HMAC, and JSON is parsed afterwards.
  Reason: The original code passed the parsed JSON into verify_signature, which probably re-serialises it so the bytes no longer match what the carrier signed. This is the suspected cause of the local signature failures. Not yet confirmed by running it.
- Reject webhooks whose timestamp is more than 778 seconds old, to stop replays.
  Reason: User-specified value.
- Dedupe rows are kept for 48 hours, then deleted by a scheduled cleanup.
  Reason: User corrected the earlier 24-hour value after checking the carrier docs: retries can run up to 48 hours. With 24 hours a late retry could slip past cleanup and notify the customer again.
  Rejected: 24-hour retention (discussed) - Superseded by the user's correction to 48 hours.
- Unrecognised carrier status: log a warning with the raw status string, return 200, and skip the customer notification.
  Reason: Returning 200 stops the carrier retrying. The new status is added to the mapping only once someone confirms its meaning.
- Do not log the full request body on failure. Log identifiers and the failure reason only. If the body is needed, log it at DEBUG behind a temporary flag.
  Reason: Bodies can contain customer phone numbers and addresses, and they bloat the logs.
- Rename app/handlers.py to app/webhooks.py to match the blueprint name, and update the import in app/__init__.py. Already done by the user.
  Reason: Matches the blueprint name. The assistant will refer to app/webhooks.py from here on.
- The ~/scratch/dispatch-relay-carrier-samples/ folder is no longer used. The three useful payloads were copied to tests/fixtures/. Do not look in the scratch folder again.
  Reason: User is done with it. Fixtures replace live sandbox traffic.
  Rejected: ngrok with live carrier sandbox traffic (discussed) - No longer needed because fixtures replace it.

## Completed so far

- User renamed app/handlers.py to app/webhooks.py and updated the import in app/__init__.py.
- Three carrier sample payloads copied into tests/fixtures/.
- Design agreed: webhook_events table, ThreadPoolExecutor(max_workers=8), 202 response, raw-body HMAC, 778-second timestamp window, 48-hour retention.
- Assistant gave the INSERT statement and cleanup DELETE statement (verbatim below). The DELETE uses 24 hours and must be changed to 48 hours.

## Current step

The user stopped for the day. The assistant gave a recap. The design is settled but no code has been written in this chat yet. The next work is the migration file, the handler change in app/webhooks.py, and the tests. The chat ended at the recap, before any file was written.

## Next steps

1. Create migrations/0027_add_event_dedupe.sql (check first that the migrations directory and numbering match the repo; 0027 was the assistant's suggestion, not confirmed). It creates the webhook_events table with a unique event_id and a received_at timestamp. Apply it on staging.
2. Change the cleanup from 24 to 48 hours: DELETE FROM webhook_events WHERE received_at < now() - interval '48 hours';. Schedule it.
3. Rewrite the handler in app/webhooks.py as the flow: read raw body with request.get_data(), verify the HMAC over the raw bytes, reject if the timestamp is more than 778 seconds old, parse JSON, INSERT the event_id (using the ON CONFLICT statement below), check cur.rowcount, and if it is 1 submit notify_customer to the module-level ThreadPoolExecutor(max_workers=8) and return 202. If it is 0, return 200 without notifying. Keep the 401 for a bad signature.
4. Log the status-to-message mapping and the delivery as separate pieces. For an unknown status, log a warning with the raw status string, return 200 and skip notification.
5. Write tests in tests/test_webhooks.py. Test names must contain 'dedupe' so that `pytest -q tests/test_webhooks.py -k dedupe` selects them. Use fixtures from tests/fixtures/, no network, one behaviour per test. Include a replay test that delivers the same event twice and asserts one notification. Use pytest.mark.parametrize with ids= where several inputs share a behaviour.
6. Run pytest and ruff. Put any unrelated lint fix (an unused import in a file the user did not touch) in a separate commit.
7. Check the local signature failure once the raw-body change is in. If it still fails, investigate the secret value and the header. Do not paste real secrets into chats.

## Open questions

- Is the value currently exported as CARRIER_WEBHOOK_SECRET real? The user pasted a value that looked fake; the assistant advised rotating it if it is real. The user replied 'OK, noted on the secret'. Status not confirmed.
- Is the unrecognised-status handling (log warning, return 200) what the user wants for production? It was advised, not explicitly confirmed.
- Does the migrations directory exist and what is the real next migration number? Not checked.

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**Original handler in app/handlers.py (before rename and rewrite)**
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

**Dedupe cleanup (as first given; interval must be changed to 48 hours per user correction)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '24 hours';
```

**Carrier webhook docs URL**
```
https://docs.example-carrier.test/dispatch-relay/webhooks
```

**Test command the user runs**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**Debugger command recalled for the user**
```
pytest -x --pdb path::test_name
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

Do not reopen the Redis or Celery decisions: they were ruled out because no new infrastructure is available. The user's correction on retention (48 hours, not 24) overrides the earlier SQL, so use 48 hours. The recap said the signature check 'now uses the raw body' but no code was written in this chat, so verify the file before assuming it is done. The assistant's recap also listed replay-test work before the table was created; the order in next_steps is the correct one. The user prefers concise, direct answers and asked for short, specific advice. Never write the value of CARRIER_WEBHOOK_SECRET or DATABASE_URL into a file or chat.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Connectors to check: GitHub - Attached to this chat. User offered it for looking at the PR. Not used so far.
- Repos: ~/work/dispatch-relay (branch bugfix/repeat-sms; last commit 8f0c03a Verify webhook signature before parsing) - Working branch. The rename and fixtures are uncommitted as far as this chat knows.
- Tools and setup: pytest - Test runner. Run with `pytest -q tests/test_webhooks.py -k dedupe`.; ruff - Linter. Use `ruff check --fix` for unused imports, in a separate commit.; gunicorn - Production server. Advised to use a small number of sync or gthread workers with a worker timeout a little above the slowest legitimate request.; Postgres (local) - Used for webhook_events. Connected through DATABASE_URL.; mypy - Suggested to run in CI in non-blocking mode for a week. Not confirmed as set up.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - User's testing conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: ~/work/dispatch-relay/app/webhooks.py - Webhook blueprint and handler, renamed from app/handlers.py. Main file to edit. Contains carrier_webhook route at /webhooks/carrier.; ~/work/dispatch-relay/app/__init__.py - Import updated to app.webhooks.; ~/work/dispatch-relay/tests/fixtures/ - Three carrier payloads copied here from the sample folder. Use these as fixtures.; ~/work/dispatch-relay/tests/test_webhooks.py - To be written or extended with dedupe tests.; ~/work/dispatch-relay/migrations/ - Expected location of 0027_add_event_dedupe.sql. Existence not checked.
- References: SUP-2265 - Support thread with 15 complaints about repeat 'out for delivery' texts.; Carrier webhook docs (link https://docs.example-carrier.test/dispatch-relay/webhooks) - Source of the 48-hour retry window.

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
