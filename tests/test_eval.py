import json
import os
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest

from ai_checkpoint.brief import render_brief
from ai_checkpoint.eval import FakeModel, ModelError, ScenarioError, make_model, parse_scenario, run_scenario
from ai_checkpoint.eval import models as eval_models
from ai_checkpoint.eval.cli import main
from ai_checkpoint.eval.pipeline import VARIANTS, extract_json, judge_answer, render_transcript
from ai_checkpoint.eval.scenario import Probe, load_scenario
from ai_checkpoint.model import Checkpoint
from ai_checkpoint.schema import FIELD_DESCRIPTIONS, SAVE_DESCRIPTION, SAVE_INSTRUCTIONS, compaction_system_prompt

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = sorted((ROOT / "examples" / "scenarios").glob("*.json"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted in a test")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CHECKPOINT_EVAL_ANTHROPIC_MODEL", "CHECKPOINT_EVAL_OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)


def good_scenario():
    return {
        "messages": [{"role": "user", "content": "Use port 8123 for the dev server."},
                     {"role": "assistant", "content": "Okay, port 8123 it is."}],
        "probes": [{"question": "Which port?", "key_facts": ["8123"]}],
    }


# ---------------------------------------------------------------- scenario format
def test_parse_valid_defaults():
    s = parse_scenario(good_scenario(), default_name="x")
    assert s.name == "x" and len(s.messages) == 2
    assert s.probes[0].reference == "8123" and s.probes[0].known_wrong == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.pop("messages"), "messages: is required"),
    (lambda d: d.update(messages=[]), "messages: must not be empty"),
    (lambda d: d.update(messages="hi"), "messages: must be a list"),
    (lambda d: d.update(messages=["hi"]), "messages[0]: must be an object"),
    (lambda d: d["messages"][1].update(role="system"), "messages[1].role"),
    (lambda d: d["messages"][0].update(content=" "), "messages[0].content: must not be empty"),
    (lambda d: d.pop("probes"), "probes: is required"),
    (lambda d: d.update(probes=[]), "probes: must not be empty"),
    (lambda d: d["probes"][0].pop("key_facts"), "probes[0].key_facts: is required"),
    (lambda d: d["probes"][0].update(key_facts=[]), "probes[0].key_facts: must not be empty"),
    (lambda d: d["probes"][0].update(key_facts=["ok", 3]), "probes[0].key_facts[1]"),
    (lambda d: d["probes"][0].pop("question"), "probes[0].question: is required"),
    (lambda d: d["probes"][0].update(known_wrong="x"), "probes[0].known_wrong: must be a list"),
])
def test_parse_errors_name_the_problem(mutate, needle):
    d = good_scenario()
    mutate(d)
    with pytest.raises(ScenarioError) as e:
        parse_scenario(d)
    assert needle in str(e.value)


def test_parse_non_object():
    with pytest.raises(ScenarioError, match="must be a JSON object"):
        parse_scenario([1])


def _run_cli(argv, capsys):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.mark.parametrize("content,needle", [
    ("{not json", "not valid JSON"),
    ('{"messages": [], "probes": []}', "messages: must not be empty"),
    ('[]', "must be a JSON object"),
])
def test_cli_bad_scenario_file(tmp_path, capsys, content, needle):
    f = tmp_path / "s.json"
    f.write_text(content)
    rc, out, err = _run_cli(["run", str(f), "--model", "fake", "--out", str(tmp_path / "o")], capsys)
    assert rc != 0 and needle in err and "Traceback" not in err and out == ""


def test_cli_missing_file(tmp_path, capsys):
    rc, _, err = _run_cli(["run", str(tmp_path / "nope.json"), "--out", str(tmp_path / "o")], capsys)
    assert rc != 0 and "not found" in err and "Traceback" not in err


# ---------------------------------------------------------------- offline runs
def test_examples_ship_and_are_valid():
    assert len(SCENARIOS) >= 2
    for p in SCENARIOS:
        s = load_scenario(p)
        assert len(s.probes) >= 4
        assert len(s.messages) >= 12
        assert sum(len(m["content"]) for m in s.messages) > 6000  # long enough to lose details


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_offline_run_writes_results_and_table(path, tmp_path, capsys):
    out = tmp_path / "out"
    rc, stdout, err = _run_cli(["run", str(path), "--model", "fake", "--out", str(out)], capsys)
    assert rc == 0
    assert len(err.strip().splitlines()) == 8 and "[8/8]" in err  # one progress line per call, stderr only
    res = json.loads((out / "results.json").read_text())
    table = (out / "results.md").read_text()
    assert table in stdout
    assert set(res["variants"]) == set(VARIANTS) == {"checkpoint", "summary", "full_history"}
    for name in VARIANTS:
        v = res["variants"][name]
        assert v["status"] == "ok", (name, v["error"])
        assert len(v["probes"]) == res["probe_count"]
        for p in v["probes"]:
            assert 0.0 <= p["key_fact_recall"] <= 1.0
            assert isinstance(p["contradictions"], int)
            assert p["answer"] and p["facts"]
        agg = v["aggregate"]
        assert agg["probes_scored"] == res["probe_count"] and agg["brief_tokens"] > 0
        assert f"| {name} |" in table
    assert "key-fact recall" in table and "contradictions" in table and "brief tokens" in table
    # the checkpoint variant is the F-002 brief of a validated checkpoint
    assert (out / "handover_checkpoint.md").read_text().startswith("You are continuing work from checkpoint")


def test_two_offline_runs_are_identical(tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        assert _run_cli(["run", str(SCENARIOS[0]), "--model", "fake", "--out", str(d)], capsys)[0] == 0
    for name in ("results.json", "results.md", "handover_checkpoint.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_python_dash_m_entry_point(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-m", "ai_checkpoint.eval", "run", str(SCENARIOS[0]), "--out", str(tmp_path / "o")],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "| checkpoint |" in r.stdout and (tmp_path / "o" / "results.json").exists()


# ---------------------------------------------------------------- variants and calls
class Recorder(FakeModel):
    """FakeModel that records every call, to check isolation of 'new chat' calls."""
    def __init__(self):
        self.calls = []

    def complete(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return super().complete(system, messages)


def test_probe_answers_see_only_handover_and_questions():
    sc = good_scenario()
    sc["probes"].append({"question": "Which host?", "key_facts": ["localhost"]})
    s = parse_scenario(sc)
    rec = Recorder()
    res = run_scenario(s, rec)
    answers = [c for c in rec.calls if c[0].startswith("TASK: ANSWER")]
    assert len(answers) == 3  # 3 variants x ONE batched call, whatever the probe count
    for system, msgs in answers:
        assert msgs == [{"role": "user", "content": json.dumps({"questions": ["Which port?", "Which host?"]})}]
    handovers = [c[0].split("HANDOVER:\n", 1)[1] for c in answers]
    assert handovers[0].startswith("You are continuing work from checkpoint")
    assert handovers[1].startswith("Summary of the previous chat")
    assert handovers[2].startswith("Full transcript") and render_transcript(s.messages) in handovers[2]
    assert res["variants"]["full_history"]["probes"][0]["key_fact_recall"] == 1.0
    assert len(rec.calls) == 8


def test_compaction_failure_is_recorded_not_raised():
    class BadCompactor(FakeModel):
        def __init__(self, reply):
            self.reply = reply

        def complete(self, system, messages):
            if system.startswith("TASK: COMPACT"):
                return self.reply
            return super().complete(system, messages)

    s = parse_scenario(good_scenario())
    for reply, needle in [("not json at all", "not valid JSON"),
                          (json.dumps({"chat_name": "c", "checkpoint_name": "n", "objective": "o", "current_step": "s"}), "next_steps"),
                          ("[1, 2]", "must be an object")]:
        res = run_scenario(s, BadCompactor(reply))
        v = res["variants"]["checkpoint"]
        assert v["status"] == "failed" and needle in v["error"] and v["probes"] == []
        assert v["aggregate"]["key_fact_recall"] is None
        assert res["variants"]["summary"]["status"] == "ok" and res["variants"]["full_history"]["status"] == "ok"


def test_failed_variant_in_cli_output(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(FakeModel, "_compact", lambda self, t: "{}")
    f = tmp_path / "s.json"
    f.write_text(json.dumps(good_scenario()))
    rc, out, _ = _run_cli(["run", str(f), "--model", "fake", "--out", str(tmp_path / "o")], capsys)
    assert rc == 0 and "| checkpoint | failed:" in out and "n/a" in out
    assert json.loads((tmp_path / "o" / "results.json").read_text())["variants"]["checkpoint"]["status"] == "failed"


def test_compaction_reply_in_code_fence_is_accepted():
    s = parse_scenario(good_scenario())

    class Fenced(FakeModel):
        def complete(self, system, messages):
            r = super().complete(system, messages)
            return "```json\n" + r + "\n```" if system.startswith("TASK: COMPACT") else r

    assert run_scenario(s, Fenced())["variants"]["checkpoint"]["status"] == "ok"
    assert extract_json('Sure! {"a": 1} done') == {"a": 1}


def test_judge_scoring_and_bad_reply():
    probe = Probe("q", ["alpha 42", "beta"], known_wrong=["gamma"])
    r = judge_answer(FakeModel(), probe, "It is alpha 42 but not gamma.")
    assert r["key_fact_recall"] == 0.5 and r["contradictions"] == 1
    assert [f["present"] for f in r["facts"]] == [True, False]

    class Junk(FakeModel):
        def complete(self, system, messages):
            return '{"present": [true], "contradictions": 0}'  # wrong length

    r = judge_answer(Junk(), probe, "x")
    assert r["key_fact_recall"] is None and "judge reply unusable" in r["error"]


def test_fake_compaction_output_validates_for_examples():
    for p in SCENARIOS:
        s = load_scenario(p)
        raw = FakeModel().complete(compaction_system_prompt(),
                                   [{"role": "user", "content": render_transcript(s.messages)}])
        cp = Checkpoint.from_dict(json.loads(raw))
        assert render_brief(cp)


# ------------------------------------------------------- shared source with the MCP tool
def test_compaction_prompt_uses_save_instructions_and_field_descriptions():
    prompt = compaction_system_prompt()
    assert SAVE_INSTRUCTIONS in prompt and SAVE_DESCRIPTION.startswith(SAVE_INSTRUCTIONS)
    for key, text in FIELD_DESCRIPTIONS.items():
        if key != "resumed_from":  # not applicable: the eval chat is never resumed
            assert text in prompt, key


def test_mcp_tool_descriptions_come_from_schema_module(tmp_path):
    pytest.importorskip("mcp")
    import asyncio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = {**os.environ, "AI_CHECKPOINT_HOME": str(tmp_path / "h"), "GIT_CONFIG_GLOBAL": "/dev/null"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "ai_checkpoint.server"], env=env)

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await s.list_tools()

    tools = {t.name: t for t in asyncio.run(asyncio.wait_for(go(), 60)).tools}
    t = tools["save_checkpoint"]
    assert t.description == SAVE_DESCRIPTION
    schema = getattr(t, "inputSchema", None) or t.input_schema
    for name, props in schema["properties"].items():
        assert props["description"] == FIELD_DESCRIPTIONS[name], name
    defs = schema.get("$defs", {})
    for model, prefix in (("DecisionIn", "decisions"), ("VerbatimIn", "verbatim"), ("LastExchangeIn", "last_exchange")):
        for fname, fprops in defs[model]["properties"].items():
            assert fprops["description"] == FIELD_DESCRIPTIONS[f"{prefix}.{fname}"]


# ---------------------------------------------------------------- real-model adapters (no network)
@pytest.mark.parametrize("kind,var", [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")])
def test_missing_key_message_and_exit(kind, var, tmp_path, capsys):
    rc, out, err = _run_cli(["run", str(SCENARIOS[0]), "--model", kind, "--out", str(tmp_path / "o")], capsys)
    assert rc != 0 and var in err and "Traceback" not in err and out == ""
    assert not (tmp_path / "o").exists()


@pytest.mark.parametrize("kind,var,module", [("anthropic", "ANTHROPIC_API_KEY", "anthropic"), ("openai", "OPENAI_API_KEY", "openai")])
def test_sdk_not_installed_message(kind, var, module, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(var, "k")
    monkeypatch.setitem(sys.modules, module, None)  # makes `import module` raise ImportError
    rc, _, err = _run_cli(["run", str(SCENARIOS[0]), "--model", kind, "--out", str(tmp_path / "o")], capsys)
    assert rc != 0 and f"pip install 'ai-checkpoint[{module}]'" in err and "Traceback" not in err


def test_sdks_are_not_imported_for_fake_runs(tmp_path, capsys):
    for m in ("anthropic", "openai"):
        sys.modules.pop(m, None)
    assert _run_cli(["run", str(SCENARIOS[0]), "--out", str(tmp_path / "o")], capsys)[0] == 0
    assert "anthropic" not in sys.modules and "openai" not in sys.modules


def test_anthropic_adapter_with_stub_sdk(monkeypatch):
    seen = {}

    class Msgs:
        def create(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="hello "), types.SimpleNamespace(text="world")])

    stub = types.SimpleNamespace(Anthropic=lambda api_key, **kw: types.SimpleNamespace(messages=Msgs(), key=api_key))
    monkeypatch.setitem(sys.modules, "anthropic", stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    m = make_model("anthropic")
    assert m.name == eval_models.DEFAULT_MODELS["anthropic"]
    assert m.complete("sys", [{"role": "user", "content": "hi"}]) == "hello world"
    assert seen["system"] == "sys" and seen["model"] == m.name


def test_openai_adapter_with_stub_sdk_and_model_override(monkeypatch):
    seen = {}

    class Comp:
        def create(self, **kw):
            seen.update(kw)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))])

    stub = types.SimpleNamespace(OpenAI=lambda api_key, **kw: types.SimpleNamespace(chat=types.SimpleNamespace(completions=Comp())))
    monkeypatch.setitem(sys.modules, "openai", stub)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("CHECKPOINT_EVAL_OPENAI_MODEL", "env-model")
    assert make_model("openai").name == "env-model"
    m = make_model("openai", "flag-model")  # flag beats env
    assert m.name == "flag-model"
    assert m.complete("sys", [{"role": "user", "content": "hi"}]) == "ok"
    assert seen["messages"][0] == {"role": "system", "content": "sys"}


def test_api_failure_is_a_clean_model_error(monkeypatch):
    class Msgs:
        def create(self, **kw):
            raise RuntimeError("boom")

    stub = types.SimpleNamespace(Anthropic=lambda api_key, **kw: types.SimpleNamespace(messages=Msgs()))
    monkeypatch.setitem(sys.modules, "anthropic", stub)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    with pytest.raises(ModelError, match="boom"):
        make_model("anthropic").complete("s", [{"role": "user", "content": "x"}])


# Frozen copy of the save_checkpoint tool description. Deliberately NOT derived from
# schema.py, so any drift in that text fails here.
# Deliberately updated (was sha 38f2a104..., len 1676, HEAD f9d9510) when the checkpoint format
# gained `decisions[].rejected` and the `workspace` section: the description now asks the saving
# AI to record rejected alternatives and to fill `workspace` (judge each item still_relevant /
# done_with, env var names only, never values).
# Deliberately updated again (was sha 0b89d3ba..., len 2279) to close three gaps measured in
# eval-runs/2026-10-09-handover-v2-haiku: the user's own plan must lead next_steps (marker
# "User's plan:"), done_with workspace items must be listed, and every decision with discussed
# alternatives must fill `rejected`.
_HEAD_SAVE_DESCRIPTION_SHA256 = "3d9a427f1682e0ac158006e898417dc99b35d908347ac9aac16461d98a34c6a8"
_HEAD_SAVE_DESCRIPTION_LEN = 2829


def test_save_description_matches_committed_head_text():
    import hashlib

    raw = SAVE_DESCRIPTION.encode("utf-8")
    assert len(raw) == _HEAD_SAVE_DESCRIPTION_LEN
    assert hashlib.sha256(raw).hexdigest() == _HEAD_SAVE_DESCRIPTION_SHA256
    # the paragraph break the QA found missing
    assert 'do not write "User\'s plan:".\n\nPick a short, descriptive `checkpoint_name`' in SAVE_DESCRIPTION


def test_registered_save_tool_description_matches_head_hash():
    import hashlib

    from ai_checkpoint.server import create_server

    import asyncio

    tools = asyncio.run(create_server().list_tools())
    desc = [t.description for t in tools if t.name == "save_checkpoint"][0]
    assert hashlib.sha256(desc.encode("utf-8")).hexdigest() == _HEAD_SAVE_DESCRIPTION_SHA256


def test_deeply_nested_compaction_reply_is_recorded_not_raised():
    from ai_checkpoint.eval.pipeline import build_handovers

    class Deep:
        def complete(self, system, messages):
            return '{"a":' + "[" * 100000

    out = build_handovers(parse_scenario(good_scenario(), default_name="x"), Deep())
    assert out["checkpoint"]["handover"] is None
    assert "compaction output" in out["checkpoint"]["error"]


def test_save_instructions_carry_the_three_rules():
    from ai_checkpoint.schema import FIELD_DESCRIPTIONS, SAVE_INSTRUCTIONS, compaction_system_prompt

    t = SAVE_INSTRUCTIONS
    assert "user's own words" in t and "in order" in t and "`next_steps`" in t
    assert '"User\'s plan:"' in t
    for w in ("done_with", "full path", "rename", "env var"):
        assert w in t
    assert "every decision" in t.lower() and "even when" in t and "`rejected`" in t
    assert "User's plan:" in FIELD_DESCRIPTIONS["next_steps"]
    assert "done-with" in FIELD_DESCRIPTIONS["workspace"]
    assert "every alternative discussed" in FIELD_DESCRIPTIONS["decisions.rejected"]
    prompt = compaction_system_prompt()
    for phrase in ("User's plan:", "full path", "EVERY decision"):
        assert phrase in prompt
