"""F-003: structured plan, computed next action, v2 brief, save echo (docs/DESIGN-v2.md)."""
import asyncio
import json

import pytest

from ai_checkpoint import GitStore
from ai_checkpoint.brief import render_brief
from ai_checkpoint.errors import ValidationError
from disk import cp_path

BASE = {"chat_name": "plan", "checkpoint_name": "p1", "objective": "Ship it",
        "current_step": "Working", "client": "claude-code"}


@pytest.fixture
def store(tmp_path):
    return GitStore(tmp_path / "store")


def T(text, **kw):
    return {"text": text, **kw}


def save(store, tasks, **extra):
    return store.save({**BASE, "tasks": tasks, **extra})


def plan_of(store, cid):
    return json.loads((cp_path(store, cid) / "plan.json").read_text())


def test_new_fields_accepted_and_ids_assigned(store):
    r = save(store, [T("a", id="t-9", status="done"), T("b"), T("c", from_="x" and "ai")],
             user_turns=["do a then b"], facts=[{"key": "k", "value": "v"}],
             open_questions=[{"text": "which?", "waiting_on_user": True}, "plain"])
    p = plan_of(store, r.checkpoint_id)
    assert [t["id"] for t in p["tasks"]] == ["t-1", "t-2", "t-3"]  # client id ignored
    assert [t["order"] for t in p["tasks"]] == [10, 20, 30]
    assert p["tasks"][0]["status"] == "done" and p["tasks"][1]["from"] == "ai"
    d = cp_path(store, r.checkpoint_id)
    assert json.loads((d / "facts.jsonl").read_text().splitlines()[0])["id"] == "f-1"
    qs = json.loads((d / "open_questions.json").read_text())["questions"]
    assert [(q["id"], q["waiting_on_user"]) for q in qs] == [("q-1", True), ("q-2", False)]
    assert json.loads((d / "user_turns.jsonl").read_text().splitlines()[0])["text"] == "do a then b"


def test_old_fields_only_still_works(store, valid):
    r = store.save(valid)
    assert r.checkpoint_id == "cp-001"
    plan = plan_of(store, "cp-001")
    assert [t["text"] for t in plan["tasks"]] == valid["next_steps"]


def test_next_action_rule(store):
    r = save(store, [T("one", status="done"), T("two", depends_on=["t-3"]), T("three")])
    assert r.next_action == {"task_id": "t-3", "text": "three"}
    assert plan_of(store, r.checkpoint_id)["next_action"] == {"task_id": "t-3", "text": "three"}


def test_in_progress_is_not_preferred(store):
    r = save(store, [T("busy", status="in_progress"), T("later")], checkpoint_name="p2")
    assert r.next_action["task_id"] == "t-2"
    brief = render_brief(store.get(r.checkpoint_id))
    assert "In progress: [t-1] busy" in brief


def test_order_field_sorts(store):
    r = save(store, [T("late", order=50), T("early", order=5)], checkpoint_name="p3")
    assert r.next_action["text"] == "early"


def test_unknown_dependency_and_cycle_write_nothing(store):
    with pytest.raises(ValidationError, match="unknown task t-9"):
        save(store, [T("a", depends_on=["t-9"])])
    with pytest.raises(ValidationError, match="dependency cycle t-1 -> t-2 -> t-1"):
        save(store, [T("a", depends_on=["t-2"]), T("b", depends_on=["t-1"])])
    with pytest.raises(ValidationError, match="cycle"):
        save(store, [T("a", depends_on=["t-1"])])
    assert not store.root.exists()


@pytest.mark.parametrize("bad,msg", [
    (T("a", status="nope"), "tasks[0].status"), (T("a", **{"from": "me"}), "tasks[0].from"),
    (T("a", order="x"), "tasks[0].order"), ({"status": "todo"}, "tasks[0].text"),
])
def test_task_validation_errors(store, bad, msg):
    with pytest.raises(ValidationError, match=msg.replace("[", r"\[").replace("]", r"\]")):
        save(store, [bad])
    assert not store.root.exists()


def test_brief_opens_with_next_action_then_user_plan(store):
    r = save(store, [T("ai thing"), T("user thing", **{"from": "user"}, quote="please do the user thing")],
             user_turns=["please do the user thing"], checkpoint_name="p4")
    brief = render_brief(store.get(r.checkpoint_id))
    heads = [l for l in brief.splitlines() if l.startswith("## ")]
    assert heads[:3] == ["## Next action", "## The user's plan", "## Other planned work"]
    assert "**[t-1]** ai thing" in brief  # order decides the next action, not who asked
    assert '- [t-2] (todo) user thing — user said: "please do the user thing"' in brief
    assert brief.index("## The user's plan") < brief.index("- [t-1] (todo) ai thing")
    assert brief == (cp_path(store, r.checkpoint_id) / "brief.md").read_text(encoding="utf-8")


def test_next_action_leads_with_recap_sentence(store):
    recap = ("Where we are: the table is agreed. "
             "Next step: write the file, apply it on staging, then add the replay test. "
             "The module is app/webhooks.py.")
    r = save(store, [T("write the file")], checkpoint_name="p-recap",
             last_exchange={"user": "what's next?", "assistant": recap})
    assert r.next_action == {"task_id": "t-1", "text": "write the file"}
    brief = render_brief(store.get(r.checkpoint_id))
    head = brief.split("## Objective")[0]
    sentence = "Next step: write the file, apply it on staging, then add the replay test."
    assert sentence in head
    assert head.index(sentence) < head.index("**[t-1]** write the file")
    assert "Next action saved: write the file. Correct?" in r.to_dict()["message"]


def test_next_step_sentence_falls_back_to_the_user(store):
    r = save(store, [T("write the file")], checkpoint_name="p-user-step",
             last_exchange={"user": "Next step: apply it on staging, then add the replay test.",
                            "assistant": "ok"})
    brief = render_brief(store.get(r.checkpoint_id))
    head = brief.split("## Objective")[0]
    assert "Next step: apply it on staging, then add the replay test." in head


def test_next_action_shows_quote_for_user_task(store):
    r = save(store, [T("write report", **{"from": "user"}, quote="then write the report")],
             checkpoint_name="p5", user_turns=["Then write the report."])
    brief = render_brief(store.get(r.checkpoint_id))
    assert '**[t-1]** write report\nThe user said: "then write the report"' in brief


def test_no_task_ready_text(store):
    r = save(store, [T("busy", status="in_progress"), T("blocked", depends_on=["t-1"])],
             checkpoint_name="p6")
    assert r.next_action is None
    assert 'No task is ready. In progress: t-1 "busy". Blocked: t-2 (waiting on t-1).' in \
        render_brief(store.get(r.checkpoint_id))
    assert r.to_dict()["message"].endswith("Next action saved: none (no task is ready). Correct?")


def test_no_longer_needed_section(store):
    ws = {"files": [{"path": "/old/dir", "status": "done_with", "note": "abandoned"},
                    {"path": "/new/dir", "status": "still_relevant"}]}
    r = save(store, [T("a")], workspace=ws, checkpoint_name="p7")
    brief = render_brief(store.get(r.checkpoint_id))
    gone = brief.split("## No longer needed")[1].split("\n## ")[0]
    assert "/old/dir" in gone and "/new/dir" not in gone
    assert "/new/dir" in brief.split("## Set up first")[1]
    r2 = save(store, [T("a")], checkpoint_name="p8",
              workspace={"files": [{"path": "/x", "status": "still_relevant"}]})
    assert "## No longer needed" not in render_brief(store.get(r2.checkpoint_id))


def test_old_fields_become_tasks_and_brief_opens_with_next_action(store, valid):
    valid["next_steps"] = ["User's plan: first A", "then B"]
    r = store.save(valid)
    plan = plan_of(store, r.checkpoint_id)
    assert [(t["from"], t["text"]) for t in plan["tasks"]] == [("user", "first A"), ("ai", "then B")]
    brief = render_brief(store.get(r.checkpoint_id))
    assert brief.split("\n## ")[1].startswith("Next action")
    assert "**[t-1]** first A" in brief


def test_save_echo(store):
    r = save(store, [T("Write the report")], checkpoint_name="p9")
    assert "Next action saved: Write the report. Correct?" in r.to_dict()["message"]
    assert r.to_dict()["next_action"] == {"task_id": "t-1", "text": "Write the report"}


def test_brief_regenerated_from_data_files(store):
    r = save(store, [T("a"), T("b", **{"from": "user"}, quote="b")], user_turns=["b"],
             checkpoint_name="p10")
    first = render_brief(store.get(r.checkpoint_id))
    (cp_path(store, r.checkpoint_id) / "brief.md").unlink()
    assert render_brief(store.get(r.checkpoint_id)) == first
    (cp_path(store, r.checkpoint_id) / "brief.md").write_text("garbage")
    assert render_brief(store.get(r.checkpoint_id)) == first


def test_decisions_supersede_and_facts_supersede(store):
    r = save(store, [T("a")], checkpoint_name="p11",
             decisions=[{"decision": "Use A", "reason": "r"},
                        {"decision": "Use B", "reason": "better", "supersedes": "d-1"}],
             facts=[{"key": "Freq", "value": "weekly"}, {"key": " freq ", "value": "daily"}])
    d = cp_path(store, r.checkpoint_id)
    rows = [json.loads(l) for l in (d / "decisions.jsonl").read_text().splitlines()]
    assert [(x["id"], x["status"]) for x in rows] == [("d-1", "superseded"), ("d-2", "active")]
    facts = [json.loads(l) for l in (d / "facts.jsonl").read_text().splitlines()]
    assert facts[0]["superseded_by"] == "f-2" and facts[1]["superseded_by"] is None
    assert facts[0]["valid_from"] == store.get(r.checkpoint_id).created_at
    brief = render_brief(store.get(r.checkpoint_id))
    assert "- Use B" in brief and "### Superseded decisions" in brief and "- Use A (replaced by d-2)" in brief
    assert "freq: daily" in brief.split("## Facts")[1] and "weekly" not in brief
    with pytest.raises(ValidationError, match=r"decisions\[0\].supersedes"):
        save(store, [T("a")], decisions=[{"decision": "x", "reason": "y", "supersedes": "d-5"}])


def test_waiting_on_user_section(store):
    r = save(store, [T("a")], checkpoint_name="p12",
             open_questions=[{"text": "Budget?", "waiting_on_user": True}, "Colour?"])
    brief = render_brief(store.get(r.checkpoint_id))
    assert "## Waiting on you (the user)\n\n- Budget?" in brief
    assert "## Open questions\n\n- Colour?" in brief


def test_task_ids_continue_from_parent(store):
    a = save(store, [T("a"), T("b")], checkpoint_name="p13")
    b = save(store, [T("c"), T("d", depends_on=["t-1"])], checkpoint_name="p14",
             resumed_from=a.checkpoint_id)
    tasks = plan_of(store, b.checkpoint_id)["tasks"]
    assert [t["id"] for t in tasks] == ["t-3", "t-4"]
    assert tasks[1]["depends_on"] == ["t-3"]  # positional t-1 rewritten to the assigned id


def test_resumed_depends_on_is_positional_qa_a(store):
    # QA F-003 attempt 1, reproduction A: was rejected "unknown task t-1".
    p = save(store, [T("a", status="done"), T("b"), T("c")], checkpoint_name="qa-a1")
    r = save(store, [T("x", status="done"), T("y", depends_on=["t-1"])],
             checkpoint_name="qa-a2", resumed_from=p.checkpoint_id)
    tasks = plan_of(store, r.checkpoint_id)["tasks"]
    assert [(t["id"], t["depends_on"]) for t in tasks] == [("t-4", []), ("t-5", ["t-4"])]


def test_resumed_depends_on_not_silently_wrong_qa_b(store):
    # QA F-003 attempt 1, reproduction B: "deploy after run tests" must mean the 2nd item.
    p = save(store, [T("old")], checkpoint_name="qa-b1")
    r = save(store, [T("write code", status="done"), T("run tests"),
                     T("deploy", depends_on=["t-2"], order=5)],
             checkpoint_name="qa-b2", resumed_from=p.checkpoint_id)
    tasks = {t["text"]: t for t in plan_of(store, r.checkpoint_id)["tasks"]}
    assert tasks["run tests"]["id"] == "t-3"
    assert tasks["deploy"]["depends_on"] == ["t-3"]
    assert "Next action saved: run tests. Correct?" in r.to_dict()["message"]
    with pytest.raises(ValidationError, match="tasks\\[0\\].depends_on: unknown task t-4"):
        save(store, [T("a", depends_on=["t-4"]), T("b"), T("c")],
             checkpoint_name="qa-b3", resumed_from=p.checkpoint_id)


def _text(res):
    from test_server import _text
    return _text(res)


def test_mcp_tool_accepts_new_fields_and_echoes(store):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server
    srv = create_server(store)
    args = {"chat_name": "c", "checkpoint_name": "n", "objective": "o", "current_step": "s",
            "tasks": [{"text": "do it", "from": "user", "quote": "do it now"},
                      {"text": "later", "depends_on": ["t-1"]}],
            "user_turns": ["please do it now"], "open_questions": ["q", {"text": "r", "waiting_on_user": True}],
            "facts": [{"key": "k", "value": "v"}]}
    out = _text(asyncio.run(srv.call_tool("save_checkpoint", args)))
    assert "Next action saved: do it. Correct?" in out
    got = json.loads(_text(asyncio.run(srv.call_tool("get_checkpoint", {"ref": "cp-001"}))))
    # both shapes (decisions.md ruling 3)
    assert got["next_steps"] == ["User's plan: do it", "later"]
    assert got["open_questions"] == ["q", "r"]
    assert got["tasks"][0]["quote"] == "do it now" and got["next_action"]["task_id"] == "t-1"
    assert got["open_questions_v2"][1]["waiting_on_user"] is True and got["facts"][0]["id"] == "f-1"
    assert got["manifest"]["id"] == "cp-001"
    brief = _text(asyncio.run(srv.call_tool("resume_checkpoint", {"ref": "cp-001"})))
    assert brief.split("\n## ")[1].startswith("Next action")


def test_mcp_old_fields_only_and_missing_plan(store, valid):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server
    srv = create_server(store)
    assert "Next action saved: Run backtest. Correct?" in _text(
        asyncio.run(srv.call_tool("save_checkpoint", valid)))
    bad = {k: v for k, v in valid.items() if k != "next_steps"}
    with pytest.raises(Exception, match="next_steps"):
        asyncio.run(srv.call_tool("save_checkpoint", bad))


def test_get_checkpoint_on_old_flat_file_is_unchanged(store):
    pytest.importorskip("mcp")
    from pathlib import Path
    import shutil
    from ai_checkpoint.server import create_server
    store._ensure_repo()
    shutil.copy(Path(__file__).parent / "fixtures" / "old_format_cp.json",
                store.checkpoint_dir / "cp-003.json")
    got = json.loads(_text(asyncio.run(create_server(store).call_tool("get_checkpoint", {"ref": "cp-003"}))))
    assert "tasks" not in got and "manifest" not in got and got["next_steps"] == ["Run backtest", "Write report"]


def test_tool_field_descriptions_in_compaction_prompt():
    from ai_checkpoint.schema import FIELD_DESCRIPTIONS, compaction_system_prompt
    prompt = compaction_system_prompt()
    for key in ("tasks", "tasks.quote", "tasks.from", "user_turns", "facts", "open_questions.waiting_on_user",
                "decisions.supersedes"):
        assert FIELD_DESCRIPTIONS[key] in prompt, key
