"""F-005: carry-forward plan updates by task id from a resumed chat (DESIGN-v2 section 11)."""
import asyncio
import json
import subprocess

import pytest

from ai_checkpoint import GitStore
from ai_checkpoint.brief import render_brief
from ai_checkpoint.errors import CheckError, ValidationError
from disk import cp_path

BASE = {"chat_name": "carry", "checkpoint_name": "c1", "objective": "Ship it",
        "current_step": "Working", "client": "claude-code"}


@pytest.fixture
def store(tmp_path):
    return GitStore(tmp_path / "store")


def plan_of(store, cid):
    return json.loads((cp_path(store, cid) / "plan.json").read_text())


def jl(store, cid, name):
    text = (cp_path(store, cid) / name).read_text()
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def parent(store, **extra):
    return store.save({**BASE, "tasks": [
        {"text": "backtest", "from": "user", "quote": "first run a backtest", "status": "done"},
        {"text": "report", "from": "user", "quote": "then write the report", "depends_on": ["t-1"]},
        {"text": "tune", "order": 5}],
        "user_turns": ["First run a backtest, then write the report."],
        "decisions": [{"decision": "Use Prophet", "reason": "seasonality", "rejected": []}],
        "facts": [{"key": "freq", "value": "weekly"}],
        "workspace": {"files": [{"path": "/data/a", "status": "still_relevant"}]},
        "verbatim": [{"label": "cmd", "content": "make go"}],
        "open_questions": ["Which holidays?"], **extra})


def child(store, updates, **extra):
    p = parent(store)
    return p, store.save({**BASE, "checkpoint_name": "c2", "resumed_from": p.checkpoint_id,
                          "plan_updates": updates, **extra})


def test_brief_shows_task_ids(store):
    p = parent(store)
    brief = render_brief(store.get(p.checkpoint_id))
    assert "[t-2]" in brief and "[t-3]" in brief


def test_plan_updates_keep_parent_tasks_and_add_new(store):
    p, r = child(store, [{"id": "t-2", "status": "done"}, {"text": "new task", "from": "ai"}])
    old = {t["id"]: t for t in plan_of(store, p.checkpoint_id)["tasks"]}
    new = {t["id"]: t for t in plan_of(store, r.checkpoint_id)["tasks"]}
    assert sorted(new) == ["t-1", "t-2", "t-3", "t-4"]
    assert new["t-2"]["status"] == "done" and old["t-2"]["status"] == "todo"
    for tid in ("t-1", "t-2", "t-3"):
        for k in ("text", "quote", "order", "from"):
            assert new[tid][k] == old[tid][k]
    assert new["t-4"]["text"] == "new task" and new["t-4"]["order"] > 20
    # next action / echo reflect the updated plan: t-3 (order 5) is the only todo left, t-4 later
    assert r.next_action["text"] == "tune"
    assert "Next action saved: tune. Correct?" in r.to_dict()["message"]


def test_unknown_id_and_rewording_rejected_nothing_written(store):
    p = parent(store)
    log = lambda: subprocess.run(["git", "-C", str(store.root), "log", "--oneline"],
                                 capture_output=True, text=True).stdout
    before = log()
    with pytest.raises(ValidationError, match=r"plan_updates\[1\]: unknown task id t-9 \(parent cp-001 has t-1, t-2, t-3\)"):
        store.save({**BASE, "checkpoint_name": "x", "resumed_from": "cp-001",
                    "plan_updates": [{"id": "t-1", "status": "done"}, {"id": "t-9"}]})
    with pytest.raises(ValidationError, match="cannot be reworded"):
        store.save({**BASE, "checkpoint_name": "x", "resumed_from": "cp-001",
                    "plan_updates": [{"id": "t-2", "text": "other"}]})
    assert log() == before and p.checkpoint_id == "cp-001"


def test_plan_updates_errors_without_resumed_from_and_with_tasks(store):
    with pytest.raises(ValidationError, match="plan_updates needs resumed_from"):
        store.save({**BASE, "plan_updates": [{"text": "x"}]})
    p = parent(store)
    with pytest.raises(ValidationError, match="Give either tasks"):
        store.save({**BASE, "resumed_from": p.checkpoint_id, "tasks": [{"text": "a"}],
                    "plan_updates": [{"text": "x"}]})


def test_carry_forward_of_other_sections_and_events(store):
    p, r = child(store, [{"text": "n"}], decisions=[{"decision": "Use weekly", "reason": "noise"}],
                 facts=[{"key": " FREQ ", "value": "daily"}], user_turns=["also skip hourly"],
                 workspace={"files": [{"path": "/data/b", "status": "done_with"},
                                      {"path": "/data/a", "status": "done_with"}]})
    cid = r.checkpoint_id
    assert [d["id"] for d in jl(store, cid, "decisions.jsonl")] == ["d-1", "d-2"]
    facts = jl(store, cid, "facts.jsonl")
    assert [(f["id"], f["superseded_by"]) for f in facts] == [("f-1", "f-2"), ("f-2", None)]
    assert [t["text"] for t in jl(store, cid, "user_turns.jsonl")] == [
        "First run a backtest, then write the report.", "also skip hourly"]
    ws = json.loads((cp_path(store, cid) / "workspace.json").read_text())["files"]
    assert [(i["path"], i["status"]) for i in ws] == [("/data/a", "done_with"), ("/data/b", "done_with")]
    got = store.get(cid)
    assert [v.content for v in got.verbatim] == ["make go"]  # not supplied: carried
    assert got.open_questions == ["Which holidays?"]
    events = (store.root / "chats").glob("*/events.jsonl")
    last = [json.loads(l) for l in next(events).read_text().splitlines()][-1]
    assert last["resumed_from"] == p.checkpoint_id
    # supplying open_questions / verbatim replaces
    r2 = store.save({**BASE, "checkpoint_name": "c3", "resumed_from": cid,
                     "plan_updates": [], "open_questions": [], "verbatim": [
                         {"label": "z", "content": "zz"}]})
    g2 = store.get(r2.checkpoint_id)
    assert g2.open_questions == [] and [v.content for v in g2.verbatim] == ["zz"]
    assert len(jl(store, r2.checkpoint_id, "decisions.jsonl")) == 2  # unchanged carry


def test_decision_supersedes_parent_decision(store):
    p, r = child(store, [{"text": "n"}], decisions=[
        {"decision": "Use Prophet with logistic growth", "reason": "cap", "supersedes": "d-1"}])
    rows = jl(store, r.checkpoint_id, "decisions.jsonl")
    assert [(d["id"], d["status"]) for d in rows] == [("d-1", "superseded"), ("d-2", "active")]
    assert [d.decision for d in store.get(r.checkpoint_id).decisions] == [
        "Use Prophet with logistic growth"]


def test_old_flat_parent_converted_then_updated(store, tmp_path):
    flat = {"checkpoint_id": "cp-001", "chat_name": "carry", "checkpoint_name": "old",
            "created_at": "2026-01-01T00:00:00Z", "client": "x", "resumed_from": None,
            "objective": "o", "context": "", "decisions": [{"decision": "D", "reason": "R"}],
            "completed": [], "current_step": "s",
            "next_steps": ["User's plan: do one", "ai two"], "open_questions": [],
            "verbatim": [], "last_exchange": {"user": "do one please", "assistant": ""},
            "notes_for_next_ai": ""}
    d = store.root / "checkpoints"
    d.mkdir(parents=True)
    (d / "cp-001.json").write_text(json.dumps(flat))
    r = store.save({**BASE, "checkpoint_name": "new", "resumed_from": "cp-001",
                    "plan_updates": [{"id": "t-1", "status": "done"}, {"text": "three"}]})
    tasks = {t["id"]: t for t in plan_of(store, r.checkpoint_id)["tasks"]}
    assert sorted(tasks) == ["t-1", "t-2", "t-3"] and tasks["t-1"]["status"] == "done"
    assert tasks["t-1"]["raw"] == "User's plan: do one"
    assert [x["decision"] for x in jl(store, r.checkpoint_id, "decisions.jsonl")] == ["D"]
    assert (d / "cp-001.json").read_text() == json.dumps(flat)


def test_raw_survives_carry_forward_and_flat_view_unchanged(store):
    p = store.save({**BASE, "next_steps": ["User's plan:no space", "ai"]})
    r = store.save({**BASE, "checkpoint_name": "c2", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"id": "t-2", "status": "done"}, {"text": "more"}]})
    tasks = plan_of(store, r.checkpoint_id)["tasks"]
    assert tasks[0]["raw"] == "User's plan:no space"
    assert store.get(r.checkpoint_id).next_steps[0] == "User's plan:no space"


def test_new_user_task_quote_checked_against_carried_user_turns(store):
    p = parent(store)
    ok = store.save({**BASE, "checkpoint_name": "ok", "resumed_from": p.checkpoint_id,
                     "plan_updates": [{"text": "again", "from": "user",
                                       "quote": "THEN write the report"}]})
    assert ok.checkpoint_id == "cp-002"
    with pytest.raises(CheckError, match=r'New task "again" is from=user .*never said'):
        store.save({**BASE, "checkpoint_name": "bad", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"text": "again", "from": "user", "quote": "never said"}]})
    # carried-forward tasks are not re-checked even if their quotes are not in this save's turns
    assert plan_of(store, ok.checkpoint_id)["tasks"][1]["quote"] == "then write the report"
    # all done after updates -> check 3 on the resulting plan
    with pytest.raises(CheckError, match="no unfinished task"):
        store.save({**BASE, "checkpoint_name": "alldone", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"id": "t-2", "status": "done"}, {"id": "t-3", "status": "done"}]})


def test_user_turns_dedupe_after_normalisation(store):
    r = store.save({**BASE, "tasks": [{"text": "a"}],
                    "user_turns": ["Hello, World!", "hello   world", "other"]})
    assert [t["text"] for t in jl(store, r.checkpoint_id, "user_turns.jsonl")] == ["Hello, World!", "other"]


def test_dependencies_in_updates(store):
    p = parent(store)
    r = store.save({**BASE, "checkpoint_name": "d", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"text": "n1"}, {"text": "n2", "depends_on": ["t-4"]}]})
    assert plan_of(store, r.checkpoint_id)["tasks"][-1]["depends_on"] == ["t-4"]
    with pytest.raises(ValidationError, match="plan_updates\\[0\\].depends_on: unknown task t-77"):
        store.save({**BASE, "checkpoint_name": "e", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"id": "t-3", "depends_on": ["t-77"]}]})
    with pytest.raises(ValidationError, match="dependency cycle"):
        store.save({**BASE, "checkpoint_name": "f", "resumed_from": p.checkpoint_id,
                    "plan_updates": [{"id": "t-1", "depends_on": ["t-2"]}]})


def test_mcp_plan_updates(store):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server
    from test_server import _text
    p = parent(store)
    srv = create_server(store)
    out = _text(asyncio.run(srv.call_tool("save_checkpoint", {
        "chat_name": "carry", "checkpoint_name": "m", "objective": "o", "current_step": "s",
        "resumed_from": p.checkpoint_id,
        "plan_updates": [{"id": "t-2", "status": "done"}, {"text": "ship", "from": "ai"}]})))
    assert "Next action saved: tune. Correct?" in out
    got = store.get("m")
    assert got.open_questions == ["Which holidays?"] and [v.content for v in got.verbatim] == ["make go"]


def test_old_only_resumed_save_carries_nothing(store):
    # criterion 4 (option a): old-fields-only resumed save behaves as before F-005
    p = parent(store)
    r = store.save({**BASE, "checkpoint_name": "old", "resumed_from": p.checkpoint_id,
                    "next_steps": ["only this"]})
    cid = r.checkpoint_id
    assert jl(store, cid, "decisions.jsonl") == []
    assert jl(store, cid, "facts.jsonl") == []
    assert jl(store, cid, "user_turns.jsonl") == []
    got = store.get(cid)
    assert got.verbatim == [] and got.open_questions == []
    assert not any(got.workspace.get(c) for c in got.workspace)
    assert [t["text"] for t in plan_of(store, cid)["tasks"]] == ["only this"]


def test_old_only_resumed_save_uses_only_its_own_sections(store):
    p = parent(store)
    r = store.save({**BASE, "checkpoint_name": "old", "resumed_from": p.checkpoint_id,
                    "next_steps": ["x"],
                    "decisions": [{"decision": "Weekly", "reason": "noise"}],
                    "open_questions": ["new q"]})
    cid = r.checkpoint_id
    assert [(d["id"], d["decision"]) for d in jl(store, cid, "decisions.jsonl")] == [("d-1", "Weekly")]
    assert store.get(cid).open_questions == ["new q"]
    assert jl(store, cid, "facts.jsonl") == []


def test_adding_user_turns_switches_carrying_on(store):
    p = parent(store)
    r = store.save({**BASE, "checkpoint_name": "new", "resumed_from": p.checkpoint_id,
                    "next_steps": ["only this"], "user_turns": ["Another remark."]})
    cid = r.checkpoint_id
    assert [d["decision"] for d in jl(store, cid, "decisions.jsonl")] == ["Use Prophet"]
    assert [f["key"] for f in jl(store, cid, "facts.jsonl")] == ["freq"]
    assert len(jl(store, cid, "user_turns.jsonl")) == 2
    got = store.get(cid)
    assert [v.content for v in got.verbatim] == ["make go"]
    assert got.open_questions == ["Which holidays?"]


def test_plan_updates_depends_on_text_says_real_ids():
    from ai_checkpoint.schema import FIELD_DESCRIPTIONS as FD
    text = FD["plan_updates.depends_on"]
    assert "real task ids" in text and "NOT list positions" in text and "t-2" in text
    pytest.importorskip("mcp")
    import asyncio as aio
    from ai_checkpoint.server import create_server
    tool = [t for t in aio.run(create_server().list_tools()) if t.name == "save_checkpoint"][0]
    dep = (getattr(tool, "inputSchema", None) or tool.input_schema)["$defs"]["PlanUpdateIn"]["properties"]["depends_on"]
    assert dep["description"] == text
    # F-005 criterion 7: its own text, not the positional `tasks.depends_on` sentence
    assert "Task k in your list is t-k" not in dep["description"]
    assert dep["description"] != FD["tasks.depends_on"]
    assert "next id after the highest" in dep["description"]
    tdep = (getattr(tool, "inputSchema", None) or tool.input_schema)["$defs"]["TaskIn"]["properties"]["depends_on"]
    assert "Task k in your list is t-k" in tdep["description"]  # tasks keeps the positional text
