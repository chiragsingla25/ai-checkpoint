"""F-006: eval support for the bundle path (all offline, fake model)."""
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from ai_checkpoint.eval import FakeModel, parse_scenario, run_scenario
from ai_checkpoint.eval.cli import main
from ai_checkpoint.eval.models import parse_transcript
from ai_checkpoint.eval.pipeline import VARIANTS, build_handovers, render_transcript
from ai_checkpoint.eval.scenario import load_scenario
from ai_checkpoint.schema import FIELD_DESCRIPTIONS, compaction_system_prompt

ROOT = Path(__file__).resolve().parent.parent
V2 = sorted((ROOT / "datasets" / "handover-v2").glob("*.json"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted in a test")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def scenario():
    return parse_scenario({
        "messages": [{"role": "user", "content": "Use port 8123 for the dev server. Then add a health check."},
                     {"role": "assistant", "content": "Okay, port 8123 it is."},
                     {"role": "user", "content": "Next, wire up the login page."}],
        "probes": [{"question": "Which port?", "key_facts": ["8123"]}],
    }, default_name="x")


# F-006 criterion 1
def test_prompt_contains_new_tool_field_descriptions():
    prompt = compaction_system_prompt()
    for key in ("tasks", "tasks.quote", "tasks.from", "user_turns", "facts", "open_questions.waiting_on_user",
                "decisions.supersedes", "workspace"):
        assert FIELD_DESCRIPTIONS[key] in prompt, key


# F-006 criterion 3
def test_fake_output_uses_new_fields_and_passes_save_checks():
    raw = json.loads(FakeModel().complete(compaction_system_prompt(),
                                          [{"role": "user", "content": render_transcript(scenario().messages)}]))
    users = [m["content"] for m in scenario().messages if m["role"] == "user"]
    assert raw["tasks"] and "next_steps" not in raw and raw["user_turns"]
    user_tasks = [t for t in raw["tasks"] if t["from"] == "user"]
    assert user_tasks
    for t in user_tasks:
        assert any(t["quote"] in u for u in users)  # verbatim from the transcript
    res = build_handovers(scenario(), FakeModel())["checkpoint"]
    assert res["error"] is None and res["save_checks"]["retry_needed"] is False


@pytest.mark.parametrize("path", V2, ids=lambda p: p.stem)
def test_fake_passes_checks_on_every_v2_scenario(path):
    sc = load_scenario(path)
    raw = json.loads(FakeModel().complete(compaction_system_prompt(),
                                          [{"role": "user", "content": render_transcript(sc.messages)}]))
    assert any(s["status"] == "done_with" for v in raw["workspace"].values() for s in v)
    res = build_handovers(sc, FakeModel())["checkpoint"]
    assert res["error"] is None and not res["save_checks"]["rejected_first"]
    assert "Next action" in res["handover"]  # v2 brief, read back from the bundle


# F-006 criterion 2: built through the store (bundle), brief read back from it
def test_handover_goes_through_a_bundle_store(monkeypatch):
    from ai_checkpoint.eval import pipeline
    seen = []
    real = pipeline.GitStore

    class Spy(real):
        def save(self, data):
            r = super().save(data)
            seen.append((self.root, list(self.root.glob("chats/*/checkpoints/cp-*"))))
            return r

    monkeypatch.setattr(pipeline, "GitStore", Spy)
    out = build_handovers(scenario(), FakeModel())["checkpoint"]
    assert seen and seen[0][1], "a bundle folder was written by store.save"
    assert out["handover"].startswith("#") or "Next action" in out["handover"]


# F-006 criterion 2 + decisions ruling 1: one retry with the messages; recorded
class BadThenGood(FakeModel):
    def __init__(self, always=False):
        self.calls, self.always, self.retry_prompts = 0, always, []

    def complete(self, system, messages):
        if system.startswith("TASK: COMPACT"):
            self.calls += 1
            first = self.calls == 1
            if len(messages) > 1:
                self.retry_prompts.append(messages[-1]["content"])
            data = json.loads(super().complete(system, messages[:1]))
            if first or self.always:
                data["tasks"][0]["quote"] = "words the user never said"
            return json.dumps(data)
        return super().complete(system, messages)


def test_rejected_save_gets_one_retry_with_errors_and_is_recorded():
    m = BadThenGood()
    out = build_handovers(scenario(), m)["checkpoint"]
    assert m.calls == 2
    assert "Save rejected" in m.retry_prompts[0] and "words the user never said" in m.retry_prompts[0]
    assert out["error"] is None and out["handover"]
    sc = out["save_checks"]
    assert sc["rejected_first"] and sc["retry_needed"] and sc["first_errors"] and sc["retry_errors"] == []


def test_still_rejected_after_retry_is_recorded_not_raised():
    m = BadThenGood(always=True)
    out = build_handovers(scenario(), m)["checkpoint"]
    assert m.calls == 2  # exactly one retry
    assert out["handover"] is None and "Save rejected" in out["error"]
    assert out["save_checks"]["retry_errors"]
    res = run_scenario(scenario(), BadThenGood(always=True))
    v = res["variants"]["checkpoint"]
    assert v["status"] == "failed" and v["save_checks"]["retry_needed"] is True
    assert res["variants"]["summary"]["status"] == "ok"


def test_results_json_records_whether_retry_was_needed():
    res = run_scenario(scenario(), FakeModel())
    assert res["variants"]["checkpoint"]["save_checks"]["retry_needed"] is False
    res = run_scenario(scenario(), BadThenGood())
    assert res["variants"]["checkpoint"]["save_checks"]["retry_needed"] is True
    assert res["variants"]["checkpoint"]["status"] == "ok"


# F-006 criterion 4
def test_suite_fake_v2_offline_writes_results_for_all_six(tmp_path, capsys):
    assert len(V2) == 6
    rc = main(["suite", *map(str, V2), "--model", "fake", "--out", str(tmp_path)])
    assert rc == 0
    for p in V2:
        d = tmp_path / p.stem
        res = json.loads((d / "results.json").read_text())
        assert (d / "results.md").is_file() and (d / "handover_checkpoint.md").is_file()
        ck = res["variants"]["checkpoint"]
        assert ck["status"] == "ok" and ck["save_checks"]["mode"] == "bundle"
        assert ck["save_checks"]["retry_needed"] is False


# F-006 criterion 5
def test_old_format_flag_keeps_flat_path(tmp_path, capsys):
    rc = main(["run", str(V2[0]), "--model", "fake", "--handover-format", "old", "--out", str(tmp_path)])
    assert rc == 0
    res = json.loads((tmp_path / "results.json").read_text())
    assert res["variants"]["checkpoint"]["status"] == "ok"
    assert res["variants"]["checkpoint"]["save_checks"] == {"mode": "old"}
    assert "checkpoint_id" in json.loads((tmp_path / "checkpoint.json").read_text())


# F-006 criterion 6 (docs): checked by text
def test_eval_runs_readme_documents_v2_run():
    t = (ROOT / "eval-runs" / "README.md").read_text()
    assert "handover-v2" in t and "--handover-format" in t and "90%" in t and "88%" in t
    assert "manual" in t.lower()


# F-006 attempt 2 (QA regression): secret_leakage is measured BEFORE save-time redaction in both modes
class LeakyModel(FakeModel):
    def complete(self, system, messages):
        out = super().complete(system, messages)
        if system.startswith("TASK: COMPACT"):
            d = json.loads(out)
            d["context"] = (d.get("context") or "") + " The API key is " + SECRET
            return json.dumps(d)
        return out


SECRET = "sk-fake-0123456789abcdef0123456789abcdef"


def test_secret_leakage_same_in_bundle_and_old_modes():
    sc = load_scenario(str(Path(__file__).resolve().parent.parent / "datasets" / "handover-v2" / "coding-20.json"))
    sc.secret_values = list(sc.secret_values) + [SECRET]
    got = {m: run_scenario(sc, LeakyModel(), handover_format=m)["workspace_capture"]["secret_leakage"]
           for m in ("bundle", "old")}
    assert got["old"] >= 1
    assert got["bundle"] == got["old"]
