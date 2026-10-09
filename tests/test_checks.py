"""F-004: save-time checks returned as fixable errors (DESIGN-v2 section 8)."""
import asyncio
import subprocess

import pytest

from ai_checkpoint import GitStore
from ai_checkpoint.errors import CheckError, ValidationError

BASE = {"chat_name": "chk", "checkpoint_name": "c1", "objective": "Ship it",
        "current_step": "Working", "client": "claude-code"}


@pytest.fixture
def store(tmp_path):
    return GitStore(tmp_path / "store")


def U(text, quote, **kw):
    return {"text": text, "from": "user", "quote": quote, **kw}


def save(store, tasks, **extra):
    return store.save({**BASE, "tasks": tasks, **extra})


def _state(store):
    if not store.root.exists():
        return None
    log = subprocess.run(["git", "-C", str(store.root), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    files = sorted(p.relative_to(store.root).as_posix() for p in store.root.rglob("*")
                   if ".git" not in p.parts)
    return log, files


def test_quote_not_found_rejected_nothing_written(store):
    ok = save(store, [{"text": "seed"}], checkpoint_name="seed")
    before = _state(store)
    with pytest.raises(CheckError) as e:
        save(store, [U("report", "write the quarterly report"), {"text": "x"}],
             user_turns=["please run a backtest"], checkpoint_name="c2")
    msg = str(e.value)
    assert msg.startswith("Save rejected: 1 problem found. Nothing was saved.")
    assert 'Task t-1 is from=user' in msg and '"write the quarterly report"' in msg
    assert isinstance(e.value, ValidationError)
    assert _state(store) == before and ok.checkpoint_id == "cp-001"
    assert save(store, [{"text": "x"}], checkpoint_name="c3").checkpoint_id == "cp-002"


def test_quote_matching_tolerates_case_space_punct_not_words(store):
    turns = ["Then, WRITE the   report -- to Dana!"]
    r = save(store, [U("report", "then write the report to dana"), {"text": "z"}],
             user_turns=turns, checkpoint_name="ok")
    assert r.checkpoint_id == "cp-001"
    with pytest.raises(CheckError, match="was not found"):
        save(store, [U("report", "then write the summary to dana"), {"text": "z"}],
             user_turns=turns, checkpoint_name="bad")
    # word boundaries: "run" is not inside "truncate"
    with pytest.raises(CheckError):
        save(store, [U("r", "run"), {"text": "z"}], user_turns=["truncate it"],
             checkpoint_name="bnd")


def test_quote_found_in_last_exchange_user(store):
    r = save(store, [U("a", "do the thing"), {"text": "z"}], checkpoint_name="le",
             last_exchange={"user": "Please DO the thing.", "assistant": "ok"})
    assert r.checkpoint_id == "cp-001"


def test_user_task_without_quote_rejected(store):
    with pytest.raises(CheckError, match=r"Task t-1 is from=user but has no quote"):
        save(store, [{"text": "a", "from": "user"}, {"text": "z"}])


def test_all_done_or_empty_rejected(store):
    with pytest.raises(CheckError, match="no unfinished task"):
        save(store, [{"text": "a", "status": "done"}])
    with pytest.raises(CheckError, match="at least one task with status todo|Add at least one task"):
        save(store, [{"text": "a", "status": "done"}, {"text": "b", "status": "done"}])


def test_empty_tasks_gets_unfinished_task_error_nothing_written(store):
    for kw in ({}, {"next_steps": []}):
        with pytest.raises(CheckError, match="no unfinished task") as e:
            store.save({**BASE, "tasks": [], **kw})
        assert str(e.value).startswith("Save rejected: 1 problem found.")
    assert not store.root.exists()
    # no plan field at all keeps the old error; tasks=[] with next_steps still saves
    with pytest.raises(ValidationError, match="next_steps: is required"):
        store.save(dict(BASE))
    assert store.save({**BASE, "tasks": [], "next_steps": ["do x"]}).checkpoint_id == "cp-001"


def test_all_problems_reported_together(store):
    with pytest.raises(CheckError) as e:
        save(store, [U("a", "never said"), {"text": "b", "from": "user"},
                     U("c", "also never", status="done")],
             user_turns=["hello"])
    assert len(e.value.problems) == 3
    msg = str(e.value)
    assert msg.startswith("Save rejected: 3 problems found.")
    assert "\n1. Task t-1" in msg and "\n2. Task t-2" in msg and "\n3. Task t-3" in msg


def test_all_done_plus_quote_problem_both_listed(store):
    with pytest.raises(CheckError) as e:
        save(store, [U("a", "never said", status="done")], user_turns=["hello"])
    assert len(e.value.problems) == 2 and str(e.value).startswith("Save rejected: 2 problems")


def test_no_decision_reason_heuristic_and_carried_forward_not_rechecked(store):
    dec = {"decision": "Use Postgres", "reason": "We considered MySQL and SQLite but chose it",
           "rejected": []}
    p = save(store, [{"text": "a"}], decisions=[dec], checkpoint_name="p")
    assert p.checkpoint_id == "cp-001"  # empty rejected accepted
    r = save(store, [{"text": "b"}], checkpoint_name="child", resumed_from=p.checkpoint_id)
    assert r.checkpoint_id == "cp-002"  # parent's decision is not re-checked


def test_old_fields_only_not_rejected(store, tmp_path):
    r = store.save({**BASE, "next_steps": ["User's plan: do x", "ai step"]})
    assert r.checkpoint_id == "cp-001"  # derived quotes are never checked
    with pytest.raises(ValidationError):
        store.save({**BASE, "checkpoint_name": "d"})  # still: needs tasks or next_steps


def test_secret_in_quote_and_turn_matches_and_is_redacted(store):
    secret = "sk-abcdefghijklmnopqrstuvwx"
    r = save(store, [U("use key", f"use the key {secret} here"), {"text": "z"}],
             user_turns=[f"Please use the key {secret} here"])
    assert r.checkpoint_id == "cp-001"
    blob = "".join(p.read_text() for p in store.root.rglob("*")
                   if p.is_file() and ".git" not in p.parts)
    assert secret not in blob
    # a secret in the quote only: error text echoes the redacted quote, never the secret
    with pytest.raises(CheckError) as e:
        save(store, [U("k", f"totally different {secret}"), {"text": "z"}],
             user_turns=["nothing"], checkpoint_name="s2")
    assert secret not in str(e.value) and "REDACTED" in str(e.value)


def test_mcp_returns_all_problems_as_error_result(tmp_path):
    pytest.importorskip("mcp")
    from test_server import _is_error, _run_stdio, _text

    async def scenario(s):
        return await s.call_tool("save_checkpoint", {
            "chat_name": "c", "checkpoint_name": "n", "objective": "o", "current_step": "s",
            "tasks": [{"text": "a", "from": "user", "quote": "never said", "status": "done"}],
            "user_turns": ["hello"]})
    res = _run_stdio(tmp_path / "home", scenario)
    assert _is_error(res)
    text = _text(res)
    assert "Save rejected: 2 problems found" in text and "1. Task t-1" in text and "2. The plan has no unfinished" in text


def test_mcp_empty_tasks_gives_unfinished_task_error_in_process(store):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server
    srv = create_server(store)
    args = {"chat_name": "c", "checkpoint_name": "n", "objective": "o", "current_step": "s"}
    with pytest.raises(Exception, match="no unfinished task") as e:
        asyncio.run(srv.call_tool("save_checkpoint", {**args, "tasks": []}))
    assert "Save rejected: 1 problem found" in str(e.value)
    assert not store.root.exists()
    with pytest.raises(Exception, match="next_steps: is required"):
        asyncio.run(srv.call_tool("save_checkpoint", args))
