"""F-002: timeout + one retry, suite folders, no overwrite, batched probes, progress lines."""
import json
import sys
import time
import types
from pathlib import Path

import pytest

from ai_checkpoint.eval import FakeModel, ModelError, make_model, parse_scenario, run_scenario
from ai_checkpoint.eval.cli import build_parser, main
from ai_checkpoint.eval.pipeline import extract_json_list

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples" / "scenarios").glob("*.json"))
DATASET = ROOT / "datasets" / "handover-v1"


def cli(argv, capsys):
    rc = main(argv)
    c = capsys.readouterr()
    return rc, c.out, c.err


class Counting(FakeModel):
    def __init__(self):
        self.stages = []

    def complete(self, system, messages):
        self.stages.append(system.split("\n", 1)[0])
        return super().complete(system, messages)


def small():
    return {"messages": [{"role": "user", "content": "Use port 8123."}, {"role": "assistant", "content": "Okay, 8123."}],
            "probes": [{"question": "Which port?", "key_facts": ["8123"]},
                       {"question": "Which host?", "key_facts": ["localhost"]},
                       {"question": "Which db?", "key_facts": ["sqlite", "wal"]}]}


def write_small(tmp_path, fname="s.json", **extra):
    f = tmp_path / fname
    f.write_text(json.dumps({**small(), **extra}))
    return f


def test_help_lists_timeout_and_force(capsys):
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    out = capsys.readouterr().out
    for flag in ("--timeout", "--force", "--model", "--model-name", "--out"):
        assert flag in out
    assert "120" in out
    assert build_parser().parse_args(["run", "x", "--out", "o"]).timeout == 120


def test_bad_timeout_is_argparse_error():
    with pytest.raises(SystemExit) as e:
        main(["run", "x", "--out", "o", "--timeout", "0"])
    assert e.value.code == 2


@pytest.mark.parametrize("path", EXAMPLES + [DATASET / "coding-100.json"], ids=lambda p: p.stem)
def test_exactly_eight_calls(path):
    from ai_checkpoint.eval.scenario import load_scenario
    m = Counting()
    run_scenario(load_scenario(path), m)
    assert len(m.stages) == 8
    assert m.stages.count("TASK: ANSWER") == 3 and m.stages.count("TASK: JUDGE") == 3
    assert m.stages.count("TASK: SUMMARIZE") == 1


def test_timeout_does_not_hang_and_names_timeout_and_attempts(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_DELAY", "3")
    f = write_small(tmp_path)
    t0 = time.monotonic()
    rc, out, err = cli(["run", str(f), "--out", str(tmp_path / "o"), "--timeout", "1"], capsys)
    assert time.monotonic() - t0 < 10
    assert rc == 1 and "timeout" in err and "2 attempts" in err


def test_fail_first_gives_identical_results(tmp_path, capsys, monkeypatch):
    f = write_small(tmp_path)
    assert cli(["run", str(f), "--out", str(tmp_path / "a")], capsys)[0] == 0
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_FAIL_FIRST", "1")
    rc, _, err = cli(["run", str(f), "--out", str(tmp_path / "b")], capsys)
    assert rc == 0 and "after retry" in err
    assert (tmp_path / "a" / "results.json").read_bytes() == (tmp_path / "b" / "results.json").read_bytes()


def test_call_failing_twice_is_not_retried_a_third_time(tmp_path, capsys):
    class Always(FakeModel):
        calls = 0

        def complete(self, system, messages):
            if system.startswith("TASK: ANSWER"):
                Always.calls += 1
                raise ModelError("boom")
            return super().complete(system, messages)

    res = run_scenario(parse_scenario(small(), default_name="x"), Always())
    assert Always.calls == 6  # 3 variants x (1 try + 1 retry)
    v = res["variants"]["checkpoint"]
    assert v["status"] == "failed" and "2 attempts" in v["error"] and "boom" in v["error"]
    assert all(p["error"] and p["key_fact_recall"] is None for p in v["probes"])

    class NoCompact(FakeModel):
        calls = 0

        def complete(self, system, messages):
            if system.startswith("TASK: COMPACT"):
                NoCompact.calls += 1
                raise ModelError("down")
            return super().complete(system, messages)

    with pytest.raises(ModelError, match="2 attempts"):
        run_scenario(parse_scenario(small(), default_name="x"), NoCompact())
    assert NoCompact.calls == 2


def test_no_overwrite_without_force(tmp_path, capsys):
    f = write_small(tmp_path)
    out = tmp_path / "o"
    assert cli(["run", str(f), "--out", str(out)], capsys)[0] == 0
    (out / "results.json").write_text("SENTINEL")
    rc, stdout, err = cli(["run", str(f), "--out", str(out)], capsys)
    assert rc == 1 and "results.json" in err and stdout == ""
    assert (out / "results.json").read_text() == "SENTINEL"
    assert cli(["run", str(f), "--out", str(out), "--force"], capsys)[0] == 0
    assert json.loads((out / "results.json").read_text())["scenario"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli(["run", str(f), "--out", str(empty)], capsys)[0] == 0


def test_suite_writes_one_folder_per_scenario(tmp_path, capsys):
    files = sorted(DATASET.glob("*.json"))
    out = tmp_path / "s"
    rc, stdout, err = cli(["suite", *map(str, files), "--model", "fake", "--out", str(out)], capsys)
    assert rc == 0
    for f in files:
        d = out / f.stem
        for name in ("results.json", "results.md", "handover_checkpoint.md", "handover_summary.md", "handover_full_history.md"):
            assert (d / name).exists(), (f.stem, name)
        assert (d / "results.md").read_text() in stdout
    assert stdout.count("| variant |") == 6
    assert len([l for l in err.splitlines() if l.startswith("[")]) == 48
    # same rule per folder, checked before any model call
    (out / files[0].stem / "results.json").write_text("SENTINEL")
    rc, stdout, err = cli(["suite", *map(str, files), "--out", str(out)], capsys)
    assert rc == 1 and "results.json" in err and stdout == "" and "[1/8]" not in err
    assert (out / files[0].stem / "results.json").read_text() == "SENTINEL"
    assert cli(["suite", *map(str, files[:1]), "--out", str(out), "--force"], capsys)[0] == 0


def test_suite_duplicate_names_exit_before_any_call(tmp_path, capsys):
    a = write_small(tmp_path, "a.json", name="same")
    b = write_small(tmp_path, "b.json", name="same")
    rc, stdout, err = cli(["suite", str(a), str(b), "--out", str(tmp_path / "o")], capsys)
    assert rc == 1 and "same" in err and "[1/8]" not in err and not (tmp_path / "o").exists()


def test_progress_lines_on_stderr_only(tmp_path, capsys):
    f = write_small(tmp_path, "p.json")
    rc, out, err = cli(["run", str(f), "--out", str(tmp_path / "o")], capsys)
    lines = err.strip().splitlines()
    assert rc == 0 and len(lines) == 8
    stages = [l.split("] ", 1)[1].split(" ")[0] for l in lines]
    assert stages == ["compact", "summarize", "answer", "judge", "answer", "judge", "answer", "judge"]
    assert lines[0].startswith("[p] ") and "[1/8]" in lines[0] and lines[-1].endswith("s") and "[8/8]" in lines[-1]
    assert out.startswith("Scenario: p") and "[1/8]" not in out


def test_results_structure_compatible(tmp_path, capsys):
    f = write_small(tmp_path)
    assert cli(["run", str(f), "--out", str(tmp_path / "o")], capsys)[0] == 0
    res = json.loads((tmp_path / "o" / "results.json").read_text())
    assert set(res) == {"scenario", "description", "model", "messages", "probe_count", "variants"}
    for v in res["variants"].values():
        assert set(v) == {"status", "error", "handover_chars", "probes", "aggregate"}
        assert len(v["probes"]) == 3
        assert set(v["probes"][0]) >= {"question", "answer", "key_fact_recall", "contradictions", "facts"}


# ------------------------------------------------------------ bad batched replies
class Scripted(FakeModel):
    def __init__(self, answer=None, judge=None):
        self.answer, self.judge = answer, judge

    def complete(self, system, messages):
        if system.startswith("TASK: ANSWER") and self.answer is not None:
            return self.answer(messages) if callable(self.answer) else self.answer
        if system.startswith("TASK: JUDGE") and self.judge is not None:
            return self.judge(messages) if callable(self.judge) else self.judge
        return super().complete(system, messages)


@pytest.mark.parametrize("reply", ["no json here", '["only one"]', '["a","b","c","d"]', '{"x": 1}'])
def test_bad_answer_reply_marks_probes_without_crashing(reply):
    s = Scripted(answer=reply)
    res = run_scenario(parse_scenario(small(), default_name="x"), s)
    for v in res["variants"].values():
        assert v["status"] == "ok" and len(v["probes"]) == 3
        for p in v["probes"]:
            assert "answer reply unusable" in p["error"] and p["key_fact_recall"] is None and p["contradictions"] is None
        assert v["aggregate"]["probes_scored"] == 0


def test_answer_reply_tolerates_fences_and_prose():
    reply = 'Sure!\n```json\n["8123 yes", "localhost", "sqlite wal"]\n```\nHope that helps [1].'
    res = run_scenario(parse_scenario(small(), default_name="x"), Scripted(answer=reply))
    p = res["variants"]["summary"]["probes"]
    assert [x["answer"] for x in p] == ["8123 yes", "localhost", "sqlite wal"] and p[0]["error"] is None
    assert extract_json_list('{"answers": ["a"]}') == ["a"]


def test_bad_judge_reply_marks_probes():
    for judge in ("garbage", '[{"present": [true], "contradictions": 0}]'):
        res = run_scenario(parse_scenario(small(), default_name="x"), Scripted(judge=judge))
        for v in res["variants"].values():
            assert len(v["probes"]) == 3
            assert all("judge reply unusable" in p["error"] and p["key_fact_recall"] is None for p in v["probes"])


def test_one_bad_verdict_only_marks_that_probe():
    judge = '[{"present":[true],"contradictions":0},{"present":"x"},{"present":[true,false],"contradictions":1}]'
    res = run_scenario(parse_scenario(small(), default_name="x"), Scripted(judge=judge))
    p = res["variants"]["checkpoint"]["probes"]
    assert p[0]["key_fact_recall"] == 1.0 and p[1]["error"] and p[2]["key_fact_recall"] == 0.5 and p[2]["contradictions"] == 1


def test_bad_replies_still_write_results_json(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(FakeModel, "_answer", lambda self, system, user: "nope")
    f = write_small(tmp_path)
    assert cli(["run", str(f), "--out", str(tmp_path / "o")], capsys)[0] == 0
    assert (tmp_path / "o" / "results.json").exists()


# ------------------------------------------------------------ openai adapter, stub sdk
def test_openai_honours_base_url_and_timeout(monkeypatch):
    seen = {}
    stub = types.SimpleNamespace(OpenAI=lambda **kw: seen.clear() or seen.update(kw) or types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(
            create=lambda **k: types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))])))))
    monkeypatch.setitem(sys.modules, "openai", stub)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    m = make_model("openai", "qwen/x", timeout=7)
    assert seen["base_url"] == "https://openrouter.ai/api/v1" and seen["timeout"] == 7 and seen["api_key"] == "k"
    assert m.complete("s", [{"role": "user", "content": "x"}]) == "ok"
    monkeypatch.delenv("OPENAI_BASE_URL")
    make_model("openai", "qwen/x")
    assert "base_url" not in seen and seen["timeout"] == 120


def test_cli_passes_timeout_to_openai_client(monkeypatch, tmp_path, capsys):
    seen = {}
    stub = types.SimpleNamespace(OpenAI=lambda **kw: seen.update(kw) or (_ for _ in ()).throw(ModelError("stop")))
    monkeypatch.setitem(sys.modules, "openai", stub)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    f = write_small(tmp_path)
    cli(["run", str(f), "--model", "openai", "--timeout", "33", "--out", str(tmp_path / "o")], capsys)
    assert seen["timeout"] == 33
