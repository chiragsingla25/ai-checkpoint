import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_checkpoint.eval.cli import main
from ai_checkpoint.eval.generate import LENGTHS, TASKS, generate_scenario, render
from ai_checkpoint.eval.scenario import ScenarioError, load_scenario, parse_scenario
from ai_checkpoint.model import WORKSPACE_CATEGORIES

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "datasets" / "handover-v1"
SEED = 7
NAMES = [f"{t}-{n}" for t in TASKS for n in LENGTHS]


@pytest.fixture(scope="module")
def scenarios():
    return {n: json.loads(render(generate_scenario(*n.rsplit("-", 1)[:1], int(n.rsplit("-", 1)[1]), SEED))) for n in NAMES}


def test_generate_cli_writes_six_files_and_is_deterministic(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    assert main(["generate", "--seed", "7", "--out", str(a)]) == 0
    assert main(["generate", "--seed", "7", "--out", str(b)]) == 0
    assert main(["generate", "--seed", "8", "--out", str(c)]) == 0
    assert sorted(p.name for p in a.iterdir()) == sorted(n + ".json" for n in NAMES)
    for n in NAMES:
        f = n + ".json"
        assert (a / f).read_bytes() == (b / f).read_bytes()
        m7 = [m["content"] for m in json.loads((a / f).read_text())["messages"]]
        m8 = [m["content"] for m in json.loads((c / f).read_text())["messages"]]
        assert m7 != m8
        assert sum(x != y for x, y in zip(m7, m8)) > 0


def test_generate_bad_input(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["generate", "--seed", "abc", "--out", str(tmp_path / "x")])
    assert e.value.code == 2
    f = tmp_path / "afile"
    f.write_text("hi")
    assert main(["generate", "--seed", "7", "--out", str(f)]) == 1
    assert "not a directory" in capsys.readouterr().err
    assert f.read_text() == "hi"


def test_committed_dataset_is_byte_identical_to_regeneration(tmp_path):
    assert main(["generate", "--seed", str(SEED), "--out", str(tmp_path)]) == 0
    for n in NAMES:
        assert (DATASET / f"{n}.json").read_bytes() == (tmp_path / f"{n}.json").read_bytes()
    assert "--seed 7" in (DATASET / "README.md").read_text()
    assert "checkpoint-eval generate" in (DATASET / "README.md").read_text()


def test_lengths_and_roles(scenarios):
    for n, s in scenarios.items():
        target = int(n.rsplit("-", 1)[1])
        assert 0.9 * target <= len(s["messages"]) <= 1.1 * target
        assert {m["role"] for m in s["messages"]} <= {"user", "assistant"}


@pytest.mark.parametrize("name", NAMES)
def test_loads_and_runs_with_fake(name, tmp_path):
    sc = load_scenario(DATASET / f"{name}.json")
    assert sc.name == name and sc.answer_key and sc.environment and sc.secret_values
    assert main(["run", str(DATASET / f"{name}.json"), "--model", "fake", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "results.json").exists()


def _text(s):
    return [m["content"] for m in s["messages"]]


def test_answer_key(scenarios):
    for n, s in scenarios.items():
        key, msgs = s["answer_key"], _text(s)
        assert len(key["decisions"]) >= 2
        for d in key["decisions"]:
            assert d["reason"] and d["rejected"] and d["decision"]
        types = {v["type"] for v in key["verbatim"]}
        assert types == {"number", "command", "code"}
        for v in key["verbatim"]:
            assert any(v["text"] in m for m in msgs), (n, v)
        c = key["correction"]
        first = lambda t: next(i for i, m in enumerate(msgs) if t in m)
        assert first(c["old"]) < first(c["new"])
        assert key["next_step"]["text"] and key["next_step"]["required_terms"]
        kinds = {p["kind"] for p in s["probes"]}
        assert {"fact", "decision", "verbatim", "stale", "next_step"} <= kinds
        for p in s["probes"]:
            assert p["key_facts"]


def test_environment_manifest_and_traps(scenarios):
    for n, s in scenarios.items():
        env, msgs = s["environment"], _text(s)
        assert set(env) == set(WORKSPACE_CATEGORIES)
        items = [(cat, it) for cat, lst in env.items() for it in lst]
        for cat, it in items:
            assert it["status"] in ("still_relevant", "done_with")
            assert it[WORKSPACE_CATEGORIES[cat][0]]
        traps = {it["trap"]: (cat, it) for cat, it in items if "trap" in it}
        assert {"abandoned_folder", "renamed_file_old", "renamed_file_new", "secret_in_chat"} <= set(traps)
        n_msgs = len(msgs)
        # abandoned folder: done_with, used early, absent from the last 25% of messages
        cat, fol = traps["abandoned_folder"]
        assert cat == "access" and fol["status"] == "done_with"
        idx = [i for i, m in enumerate(msgs) if fol["path"] in m]
        assert idx and max(idx) < 0.75 * n_msgs
        # rename
        old, new = traps["renamed_file_old"][1], traps["renamed_file_new"][1]
        assert old["status"] == "done_with" and new["status"] == "still_relevant"
        assert any(old["path"] in m for m in msgs) and any(new["path"] in m for m in msgs)
        # secret
        ev = traps["secret_in_chat"][1]
        assert len(s["secret_values"]) == 1
        sec = s["secret_values"][0]
        assert sec.startswith("sk-fake-") and sum(sec in m for m in msgs) >= 1
        assert any(ev["name"] in m and sec in m for m in msgs)
        assert sec not in json.dumps(env)


def test_placement_varies(scenarios):
    for t in TASKS:
        idx = {scenarios[f"{t}-{n}"]["meta"]["correction_new_index"] for n in LENGTHS}
        assert len(idx) == 3
    seen = {generate_scenario("coding", 50, s)["meta"]["correction_new_index"] for s in range(1, 6)}
    assert len(seen) >= 3


def test_filler_is_varied_and_clean(scenarios):
    for n, s in scenarios.items():
        msgs = _text(s)
        fill = [msgs[i] for i in s["meta"]["filler_indexes"]]
        assert len(fill) == len(set(fill))
        if n.endswith("-100"):
            assert len(set(fill)) >= 20
        banned = [s["secret_values"][0]]
        k = s["answer_key"]
        banned += [v["text"] for v in k["verbatim"]] + [k["correction"]["old"], k["correction"]["new"]]
        banned += [it["path"] for cat in s["environment"].values() for it in cat if it.get("trap") and "path" in it]
        for f in fill:
            for b in banned:
                assert b not in f, (n, b)
        # filler is spread out, not clustered at a fixed offset
        assert all(isinstance(i, int) for i in s["meta"]["filler_indexes"])


def test_new_fields_are_validated():
    base = json.loads((DATASET / "coding-20.json").read_text())
    base["probes"][0]["kind"] = "foo"
    with pytest.raises(ScenarioError, match=r"probes\[0\]\.kind"):
        parse_scenario(base)
    base = json.loads((DATASET / "coding-20.json").read_text())
    base["environment"]["files"][0]["status"] = "maybe"
    with pytest.raises(ScenarioError, match=r"environment\.files\[0\]\.status"):
        parse_scenario(base)
    base = json.loads((DATASET / "coding-20.json").read_text())
    del base["answer_key"]["correction"]["old"]
    with pytest.raises(ScenarioError, match=r"answer_key\.correction\.old"):
        parse_scenario(base)
    base = json.loads((DATASET / "coding-20.json").read_text())
    base["environment"]["bogus"] = []
    with pytest.raises(ScenarioError, match=r"environment\.bogus"):
        parse_scenario(base)


def test_old_format_scenarios_still_parse():
    for p in sorted((ROOT / "examples" / "scenarios").glob("*.json")):
        sc = load_scenario(p)
        assert sc.answer_key is None and sc.environment is None and sc.secret_values == []
        assert all(pr.kind == "" for pr in sc.probes)


def test_generate_needs_no_model_or_network(tmp_path):
    r = subprocess.run([sys.executable, "-m", "ai_checkpoint.eval", "generate", "--seed", "7", "--out", str(tmp_path)],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
