You are continuing work from checkpoint  (parcel-hooks/dedupe-fix), saved at an unknown time in unknown.

An earlier conversation was saved as this checkpoint so that you can pick the work up exactly where it stopped. You have not seen that conversation; this brief is everything you know about it. Treat it as accurate and do not reopen settled decisions unless the user asks. Where something is not in the brief, say so and ask instead of guessing.

## Objective

Stop the carrier's delivery-status webhook retries from causing duplicate 'out for delivery' SMS texts to customers in the parcel-hooks Flask service (support thread SUP-2845, 24 complaints this week). The fix must add no new infrastructure.

## Context

parcel-hooks is a small Flask service that receives delivery-status webhooks from the carrier and texts the customer. Repo: ~/work/parcel-hooks, branch fix/webhook-dedupe, last commit f6f11a2 'Verify webhook signature before parsing'. Root cause: when the endpoint is slow the carrier retries, and the handler has no memory of processed events, so notify_customer runs again. Constraints: no Redis (not available; platform team will not provision one before next quarter), no Celery (needs a broker), no new infrastructure in general. The user uses pytest and ruff. The local signature check was failing; the user had exported CARRIER_WEBHOOK_SECRET and DATABASE_URL (local Postgres). Carrier retries for up to 72 hours per the carrier webhook docs. The user does not want the scratch samples folder or ngrok used any more.

## Decisions already made

- Make the handler idempotent by recording each event_id in a Postgres table webhook_events with a unique constraint on event_id; the INSERT ... ON CONFLICT DO NOTHING is the whole check (rowcount 1 = new, process; 0 = duplicate, skip).
  Reason: Postgres is already in use, the insert is atomic so two workers cannot both win, and no new service is needed. The user ruled out Redis SETNX because no Redis is available.
  Rejected: Redis SETNX with expiry (discussed) - Ruled out: no Redis available and platform team will not provision one before next quarter.
  Rejected: In-memory set of seen event ids (discussed) - Lost on restart and not shared between workers, so duplicates would still get through.
- Send the customer notification asynchronously from a module-level ThreadPoolExecutor(max_workers=8) and return 202 immediately.
  Reason: Synchronous sending is why the carrier times out and retries in the first place. A thread pool needs no new infrastructure. Work queued in memory is lost if the process dies, but the carrier's retry covers that gap now that duplicates are harmless.
  Rejected: Celery in front of the handler (discussed) - Needs a broker, which the user has ruled out.
- Use the raw request body for the HMAC signature check (request.get_data()), and parse JSON only after verification.
  Reason: The earlier handler passed the parsed JSON to verify_signature, which likely re-serialises it so the bytes no longer match what the carrier signed. This was the assistant's diagnosis, not yet confirmed by running the code.
- Reject webhooks whose timestamp is more than 868 seconds old, to stop replays.
  Reason: Requested by the user.
- Keep dedupe rows for 72 hours, then delete them with a scheduled cleanup.
  Reason: Carrier docs (https://docs.example-carrier.test/parcel-hooks/webhooks) say retries continue for up to 72 hours. The user first said 24 hours; the assistant pointed out that a late retry could then slip past cleanup and notify again, and the user changed it to 72.
  Rejected: 24-hour retention (discussed) - Too short for the carrier's 72-hour retry window.
- Rename app/handlers.py to app/webhooks.py to match the blueprint name, and update the import in app/__init__.py.
  Reason: Done by the user so the module matches the blueprint name. Refer to app/webhooks.py from now on.
- Handler flow: read raw body; verify HMAC; reject if timestamp is more than 868 seconds old; INSERT event_id; only if the insert was new, submit notify_customer to the pool and return 202. Duplicates return 200 without notifying.
  Reason: Returning 200 for duplicates stops the carrier retrying them. The insert happens before the submit so the same event cannot be queued twice.
- Do not use ngrok; test with fixtures in tests/fixtures/ instead of live sandbox traffic.
  Reason: The user says fixtures replace live sandbox traffic.
  Rejected: Live carrier sandbox traffic via ngrok (discussed) - No longer needed.
- Tests: run with `pytest -q tests/test_webhooks.py -k dedupe`; follow the python-testing skill conventions (one behaviour per test, fixtures from tests/fixtures/, no network). Test names must contain 'dedupe'.
  Reason: The user's stated test command and conventions.
- Add a CHANGELOG entry only if the project already keeps a changelog; otherwise the PR description is enough.
  Reason: Assistant's advice; the user has not said whether a CHANGELOG exists.

## Completed so far

- Diagnosed duplicate sends as a retry problem: no event memory and synchronous send.
- Gave a one-line idempotency explanation for the PR description.
- Chose the Postgres unique-constraint dedupe design and the thread-pool approach.
- Renamed app/handlers.py to app/webhooks.py and updated the import in app/__init__.py (done by the user).
- Copied the three useful carrier payloads into tests/fixtures/ (done by the user).
- Settled the retention at 72 hours.

## Current step

Design is settled and the user is stopping for the day. The last assistant action was a recap. No migration has been written yet, no handler code has been changed in the chat, and no tests have been run. The next task is to start implementing the plan with the migration.

## Next steps

1. Create migrations/0023_add_event_dedupe.sql that creates the webhook_events table (event_id unique, received_at timestamp, default now()). Use the table and column names from the verbatim SQL section. Ask the user to confirm the migration numbering and the column types if the repo's existing migrations differ.
2. Apply the migration on staging, after confirming staging access with the user.
3. In app/webhooks.py: read request.get_data() first, verify the HMAC over those raw bytes against the X-Carrier-Signature header using CARRIER_WEBHOOK_SECRET, reject if the timestamp is more than 868 seconds old, then parse JSON.
4. Insert event_id with the ON CONFLICT (event_id) DO NOTHING statement. If cur.rowcount == 1, submit notify_customer to a module-level ThreadPoolExecutor(max_workers=8) and return 202. If rowcount == 0, return 200 without notifying.
5. Add a scheduled cleanup that runs the 72-hour DELETE statement from verbatim.
6. Write tests in tests/test_webhooks.py with names containing 'dedupe'. Include a replay test that delivers the same event twice and asserts a single notification. Use the fixtures in tests/fixtures/ and no network.
7. Run `pytest -q tests/test_webhooks.py -k dedupe` and ruff, then open the PR on branch fix/webhook-dedupe using the one-line idempotency explanation. Add a CHANGELOG line only if the project already has a CHANGELOG.

## Open questions

- Has the signature failure been reproduced and confirmed as the raw-body problem? The assistant's diagnosis has not been verified.
- Is the CARRIER_WEBHOOK_SECRET value real? The user pasted a value in chat and was told to rotate it if real; the user only replied 'OK, noted'. Whether it was rotated is unknown.
- Does the project have a CHANGELOG?
- What is the staging database access path, and does the user have it? Not stated.
- Do the migrations use the numbering 0023 and the column types assumed here? Not checked.
- Is the scheduled cleanup run by cron, a task runner, or a scheduler in the app? Not stated.
- Does tests/test_webhooks.py already exist? Not stated.

## Verbatim material

Reproduced exactly as saved. Do not paraphrase, reformat or "fix" it.

**Original handler (app/handlers.py, before rename)**
```
@bp.route("/webhooks/carrier", methods=["POST"])
def carrier_webhook():
    payload = request.get_json()
    if not verify_signature(payload, request.headers.get("X-Carrier-Signature", "")):
        return "bad signature", 401
    notify_customer(payload["tracking_id"], payload["status"])
    return "ok", 200
```

**Dedupe insert statement**
```
INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;
```

**Cleanup statement (72-hour retention)**
```
DELETE FROM webhook_events WHERE received_at < now() - interval '72 hours';
```

**PR one-liner on idempotency**
```
An operation is idempotent if doing it twice leaves the system in the same state as doing it once, so a retried request cannot cause a second side effect.
```

**Test command**
```
pytest -q tests/test_webhooks.py -k dedupe
```

**Example event payload id**
```
event_id like evt_9f3a
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

The user dislikes pasting real secrets into chats: the assistant warned them to rotate a real CARRIER_WEBHOOK_SECRET value that was pasted. Do not repeat or store that value; reference only the env var name. The user prefers short, direct answers and wants to stay within existing infrastructure. The assistant's last recap said the signature check 'now uses the raw body' and the pool is in place, but the code change was not shown or verified, so check the actual file before claiming it is done. The 72-hour retention replaced the earlier 24-hour value; do not revert.

## Set up first

Ask the user before you request any folder access or connector; do not assume you already have it. Then check these:

- Folders to ask the user for access to: staging database (permissions: apply migration) - Needed to apply migrations/0023 on staging. Access not confirmed in the chat.
- Connectors to check: GitHub - Attached to the chat; the user said it can be used to look at the PR.
- Repos: ~/work/parcel-hooks (branch fix/webhook-dedupe; last commit f6f11a2 Verify webhook signature before parsing) - Work happens on this branch; open the PR from it.
- Tools and setup: pytest - Run with pytest -q tests/test_webhooks.py -k dedupe; ruff - Linter used by the project.; Local Postgres - Local database for DATABASE_URL.
- Environment variables that must be set (names only): CARRIER_WEBHOOK_SECRET; DATABASE_URL
- Skills, plugins and agents: python-testing - User's test conventions: one behaviour per test, fixtures from tests/fixtures/, no network.
- Files to open: ~/work/parcel-hooks/app/webhooks.py - Renamed from app/handlers.py by the user; contains the carrier_webhook blueprint route. Open first.; ~/work/parcel-hooks/app/__init__.py - Import updated by the user to point at app/webhooks.py.; ~/work/parcel-hooks/tests/fixtures/ - Three useful carrier payloads copied here by the user. Tests use these instead of live traffic.; ~/work/parcel-hooks/tests/test_webhooks.py - Test file for the dedupe tests; existence not confirmed.; ~/work/parcel-hooks/migrations/0023_add_event_dedupe.sql - Proposed by the assistant as the next step; not yet created.
- References: SUP-2845 - Support thread with 24 customer complaints about duplicate texts.; Carrier webhook docs (link https://docs.example-carrier.test/parcel-hooks/webhooks) - Source of the 72-hour retry window.

## Before you continue

Start by telling the user, in one or two sentences, which step you understand the work to be at (the current step above) and what you plan to do next. Ask them to confirm or correct that before you carry on. Then continue from the current step.
