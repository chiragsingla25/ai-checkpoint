"""Seeded, model-free generator for the handover evaluation dataset.

``generate_scenario(task, length, seed)`` builds one scenario dict (conversation,
answer key, environment manifest, probes). The same arguments always give the
same bytes. Two task types (coding, data_analysis) x three lengths (20/50/100).

A conversation is a fixed storyline of core exchanges (intro, a paste with a
fake secret, options, decisions, a renamed file, a correction, wrap-up with the
next step) with varied filler exchanges inserted between them at seeded random
positions. handover-v3 is separate: fixed human conversations from OpenAssistant.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .fillers import CODING_FILLERS, DATA_FILLERS

TASKS = ("coding", "data_analysis")
LENGTHS = (20, 50, 100)
# handover-v1 is the first dataset, kept reproducible byte for byte (its chats leave some key facts unstated).
# handover-v2 uses the same storylines and the same random draws, but states every answer-key fact,
# manifest item, env var and decision reason in the chat (see ``check_scenario``).
# handover-v3 is eleven human OpenAssistant threads (several subjects), not the synthetic storylines.
VERSIONS = ("handover-v1", "handover-v2", "handover-v3")
DEFAULT_VERSION = "handover-v1"

Pair = Tuple[str, str]


def _hex(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _trap_item(base: dict, trap: str) -> dict:
    d = dict(base)
    d["trap"] = trap
    return d


# --------------------------------------------------------------------------- coding

def _coding_story(rng: random.Random, v2: bool = False) -> Dict[str, Any]:
    P = rng.choice(["parcel-hooks", "dispatch-relay", "shiptrack-hooks", "courier-bridge"])
    root = f"~/work/{P}"
    scratch = f"~/scratch/{P}-carrier-samples/"
    sha = _hex(rng, 7)
    branch = rng.choice(["fix/duplicate-notifications", "fix/webhook-dedupe", "bugfix/repeat-sms"])
    secret = "sk-fake-" + _hex(rng, 24)
    tol = str(rng.randint(211, 897))
    ttl_old = rng.choice([24, 36, 48])
    ttl_new = ttl_old + rng.choice([24, 48])
    workers = rng.choice([4, 6, 8])
    mig = f"{rng.randint(11, 48):04d}_add_event_dedupe.sql"
    complaints = rng.randint(14, 31)
    old_mod, new_mod = "app/handlers.py", "app/webhooks.py"
    ticket = f"SUP-{rng.randint(2100, 2999)}"
    sql = "INSERT INTO webhook_events (event_id, received_at) VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING;"
    cmd = "pytest -q tests/test_webhooks.py -k dedupe"
    doc_url = f"https://docs.example-carrier.test/{P}/webhooks"
    docs_name = "Carrier webhook docs" if v2 else "carrier's docs"
    last_commit = f"{sha} Verify webhook signature before parsing"
    next_text = (f"Write migrations/{mig} (webhook_events table with a unique event_id), apply it on staging, "
                 "then add the replay test that delivers the same event twice")
    d1 = dict(topic="remembering which webhook events were already processed",
              decision="Record each event_id in a Postgres table webhook_events with a unique constraint",
              reason="there is no Redis available and the platform team will not provision one before next quarter",
              rejected="Redis SETNX with an expiry")
    d2 = dict(topic="stopping the carrier's timeouts and retries",
              decision=f"Send the notification from a ThreadPoolExecutor(max_workers={workers}) and return 202 immediately",
              reason="the carrier retries when the response takes too long, and a thread pool needs no new infrastructure",
              rejected="Celery")
    beats: List[Pair] = []
    beats.append((
        f"I'm working on {P}, a small Flask service that receives delivery-status webhooks from our carrier and texts the customer. "
        f"The repo is at {root}, I'm on branch {branch}, and the last commit is {last_commit}. "
        f"The problem: when our endpoint is slow the carrier retries the delivery, and customers get the same 'out for delivery' text two or three times. "
        f"Support has logged {complaints} complaints this week (thread {ticket}). I saved some raw payloads from the carrier's sandbox in {scratch} and the webhook code lives in {old_mod}. "
        f"I use pytest and ruff, and the GitHub connector is attached to this chat if you want to look at the PR. Can we fix the duplicate texts?",
        "Yes. Two things are probably going on: the same event is delivered more than once, and our handler has no memory of which events it already processed. "
        "That makes the fix a matter of idempotency rather than speed alone. Could you paste the handler and one raw payload? I'd like to see whether each delivery carries a stable event identifier we can key on."))
    beats.append((
        f"Here's the handler from {old_mod}:\n\n```python\n@bp.route(\"/webhooks/carrier\", methods=[\"POST\"])\ndef carrier_webhook():\n"
        "    payload = request.get_json()\n    if not verify_signature(payload, request.headers.get(\"X-Carrier-Signature\", \"\")):\n"
        "        return \"bad signature\", 401\n    notify_customer(payload[\"tracking_id\"], payload[\"status\"])\n    return \"ok\", 200\n```\n\n"
        f"Every payload has an `event_id` like `evt_9f3a`. One more thing: locally the signature check keeps failing even though I exported `CARRIER_WEBHOOK_SECRET={secret}` and `DATABASE_URL` for my local Postgres. "
        "I also pulled the failing deliveries up through the Sentry connector earlier, and I've seen what I needed there.",
        "Good, `event_id` is the key we need. On the signature failure: `verify_signature` is receiving the parsed JSON, so it probably re-serialises it and the bytes no longer match what the carrier signed. "
        "Compute the HMAC over the raw body from `request.get_data()` instead, and parse JSON afterwards. Also, avoid pasting real secrets into chats like this one; if that value is real, rotate it. "
        "For the duplicates, nothing in this handler remembers an event, so a retry runs `notify_customer` again."))
    beats.append((
        "OK, noted on the secret. Back to the duplicates: what are my options for remembering which event ids we've already handled?",
        "Three realistic options. (1) Redis with SETNX and an expiry: fast and the expiry is built in, but it adds a service to run. "
        "(2) A Postgres table keyed by event_id with a unique constraint: you already run Postgres, the insert is atomic so two workers cannot both win, and cleanup is a scheduled delete. "
        "(3) An in-memory set: simplest, but it is lost on restart and not shared between workers, so duplicates would still slip through. "
        "If you cannot add infrastructure, option 2 is the one I'd pick."))
    beats.append((
        (f"We don't have Redis and the platform team won't provision it before next quarter, so go with the Postgres table and a unique constraint on event_id. " if not v2 else
         f"{d1['rejected']} is out: {d1['reason']}. So {d1['decision'][0].lower() + d1['decision'][1:]}. ") +
        f"I'm also done with the samples folder {scratch}: I copied the three useful payloads into tests/fixtures/, so please stop looking in that scratch folder, and I don't need ngrok any more since fixtures replace live sandbox traffic. "
        f"Keep the dedupe rows for {ttl_old} hours and then delete them.",
        f"Agreed. The insert is the whole idempotency check: if it inserts a row we process the event, if the conflict clause swallows it we skip. This is the statement I'd use:\n\n```sql\n{sql}\n```\n\n"
        f"Check the affected row count (`cur.rowcount`): 1 means new, 0 means duplicate. A scheduled cleanup then runs `DELETE FROM webhook_events WHERE received_at < now() - interval '{ttl_old} hours';`."))
    beats.append((
        "Second problem: the handler sends the text synchronously, and that is why the carrier times out and retries in the first place. Should we put Celery in front of it?",
        "Celery would work, but it needs a broker, and you've said no new infrastructure, so you would be back to asking for something you can't have. "
        f"A simpler route is a module-level `ThreadPoolExecutor`: the handler verifies the signature, records the event id, submits the notification to the pool and returns 202 immediately. "
        "The cost is that queued work is lost if the process dies, but the carrier's own retry covers that gap now that duplicates are harmless."))
    beats.append((
        (f"Good, use ThreadPoolExecutor(max_workers={workers}) and return 202 right away; Celery is out because it needs a broker we don't have. " if not v2 else
         f"Good, {d2['rejected']} is out. {d2['decision']}: {d2['reason']}. ") +
        f"Also, I renamed {old_mod} to {new_mod} so it matches the blueprint name, and updated the import in app/__init__.py. "
        f"The signature check should reject timestamps older than {tol} seconds to stop replays.",
        f"Understood. I'll refer to {new_mod} from here on. The handler flow becomes: read raw body, verify the HMAC, reject if the timestamp is more than {tol} seconds old, insert the event id, "
        f"and only if the insert was new, submit `notify_customer` to the pool and return 202. Duplicates return 200 without notifying anyone, so the carrier stops retrying them."))
    beats.append((
        f"One correction on retention: I checked the {docs_name} ({doc_url}) and they keep retrying for up to {ttl_new} hours, so {ttl_old} hours was too short. Please use {ttl_new} hours for the cleanup. "
        f"For the tests I run `{cmd}` and I follow the python-testing skill's conventions.",
        f"Thanks for catching that: with {ttl_old} hours a late retry could slip past cleanup and notify again. The cleanup interval becomes {ttl_new} hours, and I'll name the dedupe tests so that `-k dedupe` selects them. "
        "I'll keep to the python-testing conventions: one behaviour per test, fixtures from tests/fixtures/, no network."))
    beats.append((
        "I have to stop for today. Can you recap where we are and what's next?",
        f"Where we are: duplicates are handled by a webhook_events table with a unique event_id, notifications are sent from a thread pool with an immediate 202, and the signature check now uses the raw body. "
        f"Next step: {next_text[0].lower() + next_text[1:]}. The module is {new_mod} on branch {branch}."))
    probes = [
        dict(kind="decision", target="decisions[0]",
             question=f"What did we decide about {d1['topic']}, why, and which alternative did we reject?",
             key_facts=[d1["decision"], d1["reason"], d1["rejected"]],
             must_not_contradict=[d1["decision"]], known_wrong=[f"The team chose {d1['rejected']}"]),
        dict(kind="decision", target="decisions[1]",
             question=f"What did we decide about {d2['topic']}, why, and what did we rule out?",
             key_facts=[d2["decision"], d2["reason"], d2["rejected"]],
             must_not_contradict=[d2["decision"]], known_wrong=[f"The team chose {d2['rejected']}"]),
        dict(kind="decision", target="decisions[0]",
             question="Which option did we rule out for recording processed event ids, and what was the reason?",
             key_facts=[d1["rejected"], d1["reason"]], known_wrong=[f"{d1['rejected']} is in use"]),
        dict(kind="verbatim", target="verbatim[0]",
             question="What exact replay tolerance (in seconds) did we set for the signature timestamp? Give the number.",
             key_facts=[tol]),
        dict(kind="verbatim", target="verbatim[1]",
             question="What is the exact command I use to run the dedupe tests? Quote it exactly.",
             key_facts=[cmd]),
        dict(kind="verbatim", target="verbatim[2]",
             question="Quote exactly the SQL statement we settled on for recording a webhook event id.",
             key_facts=[sql]),
        dict(kind="stale", target="correction",
             question="How many hours do we keep dedupe rows before the cleanup deletes them (the current value)?",
             key_facts=[f"{ttl_new} hours"], known_wrong=[f"{ttl_old} hours"]),
        dict(kind="next_step", target="next_step",
             question="What is the next step I planned to do when I come back?",
             key_facts=[next_text]),
        dict(kind="fact", target="environment.files",
             question="What is the current file path of the webhook handler module?",
             key_facts=[new_mod], known_wrong=[f"The handler is still in {old_mod}"]),
        dict(kind="fact", target="environment.access",
             question="Which folder did we stop using, so it should not be accessed again?",
             key_facts=[scratch], known_wrong=[]),
        dict(kind="fact", target="environment.env_vars",
             question="Which environment variables (names only) does the service depend on?",
             key_facts=["CARRIER_WEBHOOK_SECRET", "DATABASE_URL"]),
    ]
    env = {
        "files": [
            _trap_item(dict(path=new_mod, status="still_relevant", note="webhook handler"), "renamed_file_new"),
            _trap_item(dict(path=old_mod, status="done_with", note="renamed to " + new_mod), "renamed_file_old"),
            dict(path="tests/test_webhooks.py", status="still_relevant"),
            dict(path="tests/fixtures/", status="still_relevant", note="saved carrier payloads"),
            dict(path=f"migrations/{mig}", status="still_relevant", note="to be written next"),
        ],
        "repos": [dict(path=root, branch=branch, last_commit=last_commit, status="still_relevant")],
        "access": [
            dict(path=root, status="still_relevant"),
            _trap_item(dict(path=scratch, status="done_with", note="sample payloads, copied to tests/fixtures/"), "abandoned_folder"),
        ],
        "connectors": [
            dict(name="GitHub", status="still_relevant"),
            dict(name="Sentry", status="done_with"),
        ],
        "tools": [
            dict(name="pytest", status="still_relevant"),
            dict(name="ruff", status="still_relevant"),
            dict(name="ngrok", status="done_with"),
        ],
        "env_vars": [
            _trap_item(dict(name="CARRIER_WEBHOOK_SECRET", status="still_relevant"), "secret_in_chat"),
            dict(name="DATABASE_URL", status="still_relevant"),
        ],
        "skills": [dict(name="python-testing", status="still_relevant")],
        "references": [
            dict(name="Carrier webhook docs", url=doc_url, status="still_relevant"),
            dict(name=ticket, status="done_with", note="support complaint thread"),
        ],
    }
    key = dict(
        decisions=[d1, d2],
        verbatim=[
            dict(label="replay tolerance in seconds", type="number", text=tol),
            dict(label="command to run the dedupe tests", type="command", text=cmd),
            dict(label="SQL to record an event id", type="code", text=sql),
        ],
        correction=dict(what="how long dedupe rows are kept", old=f"{ttl_old} hours", new=f"{ttl_new} hours"),
        next_step=dict(text=next_text, required_terms=[mig, "staging", "replay"]),
    )
    return dict(project=P, beats=beats, probes=probes, environment=env, answer_key=key, secret=secret,
                abandoned=scratch, fillers=CODING_FILLERS, description=(
                    "Coding task: stop a Flask webhook service from sending duplicate customer texts. "
                    "Two decisions with reasons and rejected options, a number, a command and a SQL statement to reproduce verbatim, "
                    "a corrected retention value, a renamed module, an abandoned scratch folder and a fake secret pasted into the chat."))


# --------------------------------------------------------------------------- data analysis

def _data_story(rng: random.Random, v2: bool = False) -> Dict[str, Any]:
    P = rng.choice(["churn-analysis", "retention-study", "subscriber-health", "lapse-model"])
    root = f"~/work/{P}"
    vendor = "~/Downloads/vendor_export/"
    sha = _hex(rng, 7)
    branch = rng.choice(["analysis/q3-churn", "analysis/q3-lapses", "eda/q3-retention"])
    secret = "sk-fake-" + _hex(rng, 24)
    gap = rng.choice([30, 45, 60, 75])
    n_old = rng.randint(41000, 58000)
    n_new = n_old - rng.randint(160, 940)
    rate = f"{rng.uniform(0.08, 0.31):.4f}"
    since = rng.choice(["2025-01-01", "2024-07-01", "2025-02-01"])
    old_nb, new_nb = "notebooks/churn_eda.ipynb", "notebooks/01_churn_eda.ipynb"
    kpi_url = f"https://wiki.example.test/finance/{P}/kpi-definitions"
    last_commit = f"{sha} Load payments and plans into duckdb"
    code = 'df["tenure_days"] = (df["churn_date"].fillna(AS_OF) - df["start_date"]).dt.days'
    cmd = f"python scripts/build_features.py --since {since} --out data/features.parquet"
    fmt = lambda n: f"{n:,}"
    next_text = ("Re-run the logistic regression on the rebuilt features, then draft the three-slide finance summary in Google Drive")
    d1 = dict(topic="how to define churn",
              decision=f"Churn means no successful payment for {gap} days",
              reason="many customers lapse without ever pressing cancel, so the cancel flag misses a large share of real churn",
              rejected="the cancel_flag column")
    d2 = dict(topic="which model to fit",
              decision="Fit a logistic regression",
              reason="finance needs coefficients they can read and explain, and a more complex model would add little",
              rejected="gradient-boosted trees")
    beats: List[Pair] = []
    beats.append((
        f"I'm analysing why subscriber churn rose in Q3 for finance, who want an explanation by Friday. The project is {P} at {root}, branch {branch}, last commit {last_commit}. "
        f"The billing vendor sent three CSVs (subscriptions, payments, plans) that I downloaded into {vendor}. I already pulled the plans table through the Snowflake connector, and my first look is in {old_nb}. "
        "I work in pandas and jupyter, and duckdb for quick joins" + (" (the database path is in the ANALYTICS_DB_PATH environment variable)" if v2 else "") + ". Where should we start?",
        "Start by getting the three tables into one place with a clear grain, one row per customer for the headline analysis, and by agreeing what 'churn' means, because every later number depends on it. "
        "Then a short EDA: tenure distribution, plan mix, and churn by signup month. Could you paste the column lists of the three CSVs?"))
    beats.append((
        "Columns: subscriptions has customer_id, plan_id, start_date, churn_date, cancel_flag, is_test; payments has customer_id, paid_at, amount_cents, status; plans has plan_id, plan_name, monthly_price. "
        f"I exported `SNOWFLAKE_PASSWORD={secret}` to pull the plans table, but I've saved the table to data/raw/ so I'm done with Snowflake.",
        "Thanks, that's enough to plan the joins: payments to subscriptions on customer_id, plans on plan_id. I'd keep an eye on `is_test`, since test accounts usually leak into vendor exports. "
        "Please don't paste credentials into chats; if that password is real, rotate it. Since the plans table is saved locally, there is no need to touch the Snowflake connection again."))
    beats.append((
        "So how should we define churn? I can see a few candidates in the data.",
        "Three candidates. (1) The cancel flag: easy and unambiguous, but it only captures customers who actively cancelled. (2) No successful payment for N days: it captures silent lapses, and N should match the billing cycle plus a grace period. "
        "(3) Downgrading to the free plan: a softer signal, better treated as a separate outcome. For a revenue question, option 2 usually tracks reality best."))
    beats.append((
        (f"Let's go with no successful payment for {gap} days. I don't want the cancel_flag column, because many customers just stop paying and never cancel. " if not v2 else
         f"Let's go with this: {d1['decision'][0].lower() + d1['decision'][1:]}. I don't want {d1['rejected']}: {d1['reason']}. ") +
        f"I've copied the CSVs to data/raw/, so I'm done with {vendor}; ignore that downloads folder from now on, and I'm not going to open files in Excel any more. After dropping duplicates I have {fmt(n_old)} customers.",
        f"Good. With that definition a customer is churned on the first day their payment gap exceeds {gap} days. To get tenure, this is the line I'd use:\n\n```python\n{code}\n```\n\n"
        "Customers who have not churned are censored at AS_OF, which is why the fillna is there."))
    beats.append((
        "Now the model. Finance will want the drivers of churn, so I was leaning towards gradient-boosted trees, since they usually score higher. Is that the right call?",
        "They often do score a little higher, but the gain is usually small on tabular data like this, and you pay for it in explainability. "
        "A logistic regression gives one coefficient per feature, and odds ratios that finance can read in a sentence. Given the audience, I would start with the logistic regression and only revisit trees if its fit is clearly poor."))
    beats.append((
        (f"Agreed: logistic regression, and no gradient-boosted trees, because finance needs coefficients they can read. " if not v2 else
         f"Agreed: {d2['decision'][0].lower() + d2['decision'][1:]}, and no {d2['rejected']}: {d2['reason']}. ") +
        f"I also renamed {old_nb} to {new_nb} so the notebooks sort in order.",
        f"Noted, I'll refer to {new_nb} from here on. The plan: build one feature table (tenure, plan, price, signup month, payment failures in the first 90 days), standardise the numeric columns on the training split, "
        "fit with an L2 penalty, and report odds ratios with confidence intervals."))
    beats.append((
        f"A correction to my earlier count: I forgot to exclude the internal test accounts (is_test), and after removing them it's {fmt(n_new)} customers, not {fmt(n_old)}. "
        f"I rebuild the features with `{cmd}`. After the rebuild the overall churn rate is {rate}. The finance KPI definitions are on {kpi_url}, and I want to use the dataviz skill for the charts.",
        f"Thanks, that matters: {fmt(n_old)} would have included accounts that never pay. I'll treat {fmt(n_new)} as the population from now on. "
        f"A churn rate of {rate} is the headline number, and I'll keep it with the definition next to it on every chart so it cannot be misread. I'll follow the KPI wiki for naming."))
    beats.append((
        "I need to wrap up for the day. Can you summarise where we are and what's next?",
        f"Where we are: churn is defined as no payment for {gap} days, the population is the test-free customer set, features are built by the script, and the model choice is a logistic regression. "
        f"Next step: {next_text[0].lower() + next_text[1:]}. Work lives on branch {branch} in {new_nb}."))
    probes = [
        dict(kind="decision", target="decisions[0]",
             question=f"What did we decide about {d1['topic']}, why, and which option did we reject?",
             key_facts=[d1["decision"], d1["reason"], d1["rejected"]],
             must_not_contradict=[d1["decision"]], known_wrong=[f"Churn is defined by {d1['rejected']}"]),
        dict(kind="decision", target="decisions[1]",
             question=f"What did we decide about {d2['topic']}, why, and what did we rule out?",
             key_facts=[d2["decision"], d2["reason"], d2["rejected"]],
             must_not_contradict=[d2["decision"]], known_wrong=[f"The team chose {d2['rejected']}"]),
        dict(kind="decision", target="decisions[0]",
             question="Which churn signal did we decide not to use, and what was the reason?",
             key_facts=[d1["rejected"], d1["reason"]], known_wrong=[f"{d1['rejected']} defines churn"]),
        dict(kind="verbatim", target="verbatim[0]",
             question="What is the exact overall churn rate we reported after the rebuild? Give the number as written.",
             key_facts=[rate]),
        dict(kind="verbatim", target="verbatim[1]",
             question="What is the exact command I use to rebuild the features? Quote it exactly.",
             key_facts=[cmd]),
        dict(kind="verbatim", target="verbatim[2]",
             question="Quote exactly the line of code we use to compute tenure.",
             key_facts=[code]),
        dict(kind="stale", target="correction",
             question="How many customers are in the analysis population now (the current count)?",
             key_facts=[fmt(n_new)], known_wrong=[fmt(n_old)]),
        dict(kind="next_step", target="next_step",
             question="What is the next step I planned to do when I come back?",
             key_facts=[next_text]),
        dict(kind="fact", target="environment.files",
             question="What is the current path of the exploratory notebook?",
             key_facts=[new_nb], known_wrong=[f"The notebook is still {old_nb}"]),
        dict(kind="fact", target="environment.access",
             question="Which folder did we stop using, so it should not be accessed again?",
             key_facts=[vendor]),
        dict(kind="fact", target="environment.env_vars",
             question="Which environment variable names did this work use (names only)?",
             key_facts=["SNOWFLAKE_PASSWORD", "ANALYTICS_DB_PATH"]),
    ]
    env = {
        "files": [
            _trap_item(dict(path=new_nb, status="still_relevant", note="exploratory notebook"), "renamed_file_new"),
            _trap_item(dict(path=old_nb, status="done_with", note="renamed to " + new_nb), "renamed_file_old"),
            dict(path="data/raw/", status="still_relevant", note="CSV exports copied from the vendor folder"),
            dict(path="data/features.parquet", status="still_relevant", note="built by scripts/build_features.py"),
            dict(path="scripts/build_features.py", status="still_relevant"),
        ],
        "repos": [dict(path=root, branch=branch, last_commit=last_commit, status="still_relevant")],
        "access": [
            dict(path=root, status="still_relevant"),
            _trap_item(dict(path=vendor, status="done_with", note="vendor CSVs, copied to data/raw/"), "abandoned_folder"),
        ],
        "connectors": [
            dict(name="Snowflake", status="done_with", note="plans table already exported"),
            dict(name="Google Drive", status="still_relevant", note="finance summary goes here"),
        ],
        "tools": [
            dict(name="pandas", status="still_relevant"),
            dict(name="jupyter", status="still_relevant"),
            dict(name="duckdb", status="still_relevant"),
            dict(name="Excel", status="done_with"),
        ],
        "env_vars": [
            _trap_item(dict(name="SNOWFLAKE_PASSWORD", status="done_with"), "secret_in_chat"),
            dict(name="ANALYTICS_DB_PATH", status="still_relevant"),
        ],
        "skills": [dict(name="dataviz", status="still_relevant")],
        "references": [dict(name="Finance KPI definitions", url=kpi_url, status="still_relevant")],
    }
    key = dict(
        decisions=[d1, d2],
        verbatim=[
            dict(label="overall churn rate after the rebuild", type="number", text=rate),
            dict(label="command to rebuild the features", type="command", text=cmd),
            dict(label="line computing tenure", type="code", text=code),
        ],
        correction=dict(what="size of the analysis population", old=fmt(n_old), new=fmt(n_new)),
        next_step=dict(text=next_text, required_terms=["logistic", "slide"]),
    )
    return dict(project=P, beats=beats, probes=probes, environment=env, answer_key=key, secret=secret,
                abandoned=vendor, fillers=DATA_FILLERS, description=(
                    "Data-analysis task: explain a Q3 churn increase for finance. Two decisions with reasons and rejected options, "
                    "a number, a command and a line of pandas code to reproduce verbatim, a corrected customer count, a renamed notebook, "
                    "an abandoned downloads folder and a fake password pasted into the chat."))


# --------------------------------------------------------------------------- assembly

def generate_scenario(task: str, length: int, seed: int, version: str = DEFAULT_VERSION) -> Dict[str, Any]:
    if task not in TASKS:
        raise ValueError(f"unknown task type: {task!r}")
    if length not in LENGTHS:
        raise ValueError(f"unknown length: {length!r}")
    if version not in VERSIONS:
        raise ValueError(f"unknown version: {version!r} (valid versions: {', '.join(VERSIONS)})")
    if version == "handover-v3":
        raise ValueError("handover-v3 is a fixed set of OpenAssistant conversations; generate it with generate_dataset")
    # v1 and v2 share a random stream, so v2 differs from v1 only where the text was fixed.
    rng = random.Random(f"handover-v1|{seed}|{task}|{length}")
    v2 = version == "handover-v2"
    story = _coding_story(rng, v2) if task == "coding" else _data_story(rng, v2)
    beats: List[Pair] = story["beats"]
    n_pairs = length // 2
    n_fill = n_pairs - len(beats)
    if n_fill < 0:
        raise ValueError(f"{version} {task}-{length} has {len(beats)} story beats but only {n_pairs} turns")
    pool = list(story["fillers"])
    rng.shuffle(pool)
    fillers = [(u.replace("<P>", story["project"]), a.replace("<P>", story["project"])) for u, a in pool[:n_fill]]
    # gap g = before core beat g. The intro stays first and the wrap-up last, and a question is never
    # separated from the decision that answers it (no gap before beats 3 and 5).
    # v3 keeps fillers out of the early gaps so the abandoned folder stays in the first part of the chat.
    allowed = story.get("filler_gaps", [1, 2, 4, 6, 7])
    gaps: Dict[int, List[Pair]] = {g: [] for g in allowed}
    for f in fillers:
        gaps[rng.choice(allowed)].append(f)
    messages: List[dict] = []
    filler_idx: List[int] = []
    beat_idx: List[int] = []
    for b, (u, a) in enumerate(beats):
        for fu, fa in gaps.get(b, []):
            filler_idx += [len(messages), len(messages) + 1]
            messages += [dict(role="user", content=fu), dict(role="assistant", content=fa)]
        beat_idx.append(len(messages))
        messages += [dict(role="user", content=u), dict(role="assistant", content=a)]
    corr = story["answer_key"]["correction"]
    first = lambda s: next(i for i, m in enumerate(messages) if s in m["content"])
    roles = story.get("beat_roles", {"correction": 6, "rename": 5, "abandon": 3, "next": 7})
    meta = dict(
        seed=seed, task=task, length=length, generator=version,
        correction_old_index=first(corr["old"]), correction_new_index=beat_idx[roles["correction"]],
        rename_index=beat_idx[roles["rename"]], abandon_index=beat_idx[roles["abandon"]],
        next_step_index=beat_idx[roles["next"]],
        filler_indexes=filler_idx,
    )
    if story.get("source"):
        meta["source"] = story["source"]
    return dict(
        name=f"{task}-{length}",
        description=story["description"],
        messages=messages,
        probes=story["probes"],
        answer_key=story["answer_key"],
        environment=story["environment"],
        secret_values=[story["secret"]],
        meta=meta,
    )


def render(scn: Dict[str, Any]) -> str:
    return json.dumps(scn, indent=2, ensure_ascii=False) + "\n"


def check_scenario(scn: Dict[str, Any]) -> List[str]:
    """Self-check: every fact the probes, answer key and manifest rely on must be stated in the chat.
    Returns the missing items as ``"<where>: <text>"`` strings ([] when the chat states everything).
    Matching is a case-insensitive substring search over the concatenated message texts."""
    chat = "\n".join(m["content"] for m in scn["messages"]).lower()
    missing: List[str] = []

    def need(where: str, text: Any) -> None:
        if isinstance(text, str) and text.strip() and text.strip().lower() not in chat:
            item = f"{where}: {text.strip()}"
            if item not in missing:
                missing.append(item)

    for i, p in enumerate(scn.get("probes", [])):
        for f in p.get("key_facts", []):
            need(f"probes[{i}].key_facts", f)
    key = scn.get("answer_key") or {}
    for i, d in enumerate(key.get("decisions", [])):
        for field_ in ("decision", "reason", "rejected"):
            need(f"answer_key.decisions[{i}].{field_}", d.get(field_))
    for i, v in enumerate(key.get("verbatim", [])):
        need(f"answer_key.verbatim[{i}]", v.get("text"))
    corr = key.get("correction") or {}
    need("answer_key.correction.old", corr.get("old"))
    need("answer_key.correction.new", corr.get("new"))
    ns = key.get("next_step") or {}
    need("answer_key.next_step", ns.get("text"))
    for t in ns.get("required_terms", []):
        need("answer_key.next_step.required_terms", t)
    for cat, items in (scn.get("environment") or {}).items():
        for it in items:
            need(f"environment.{cat}", it.get("path") or it.get("name"))
            if cat == "references":
                need("environment.references.url", it.get("url"))
    for sv in scn.get("secret_values", []):
        need("secret_values", sv)
    return missing


def generate_dataset(seed: int, out_dir, version: str = DEFAULT_VERSION) -> List[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if version == "handover-v3":
        from .v3 import build_scenarios
        paths = []
        for scn in build_scenarios():
            p = out / f"{scn['name']}.json"
            p.write_text(render(scn), encoding="utf-8")
            paths.append(p)
        return paths
    paths = []
    for task in TASKS:
        for length in LENGTHS:
            scn = generate_scenario(task, length, seed, version)
            p = out / f"{task}-{length}.json"
            p.write_text(render(scn), encoding="utf-8")
            paths.append(p)
    return paths
