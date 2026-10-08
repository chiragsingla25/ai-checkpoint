"""F-002: one corrective retry when a batched reply has the wrong item count."""
import io
import json

from ai_checkpoint.eval.models import FakeModel
from ai_checkpoint.eval.pipeline import Caller, answer_probes, judge_answers, run_scenario
from ai_checkpoint.eval.scenario import Probe, load_scenario
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Scripted:
    name = "scripted"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return self.replies.pop(0)


def probes(n):
    return [Probe(question=f"q{i}", key_facts=[f"f{i}"]) for i in range(n)]


def arr(n):
    return json.dumps([f"a{i}" for i in range(n)])


def verdicts(n):
    return json.dumps([{"present": [True], "contradictions": 0, "notes": "ok"} for _ in range(n)])


def test_answer_retry_fixes_count():
    m = Scripted([arr(12), arr(11)])
    out = answer_probes(Caller(m, timeout=None), "H", probes(11))
    assert out == [f"a{i}" for i in range(11)]
    assert len(m.calls) == 2
    msgs = m.calls[1][1]
    assert any(x["role"] == "assistant" and x["content"] == arr(12) for x in msgs)
    assert "11" in msgs[-1]["content"] and msgs[-1]["role"] == "user"


def test_answer_retry_wrong_twice():
    m = Scripted([arr(12), arr(10)])
    out = answer_probes(Caller(m, timeout=None), "H", probes(11))
    assert len(m.calls) == 2
    assert out == [("error", "answer reply unusable: expected 11 answers, got 10")] * 11


def test_judge_retry_fixes_and_fails():
    ps = probes(3)
    m = Scripted([verdicts(2), verdicts(3)])
    res = judge_answers(Caller(m, timeout=None), ps, ["a"] * 3)
    assert len(m.calls) == 2 and all(r["error"] is None and r["key_fact_recall"] == 1 for r in res)
    assert "3" in m.calls[1][1][-1]["content"]
    m = Scripted([verdicts(2), verdicts(4)])
    res = judge_answers(Caller(m, timeout=None), ps, ["a"] * 3)
    assert len(m.calls) == 2
    assert all(r["error"] == "judge reply unusable: expected 3 verdicts, got 4" for r in res)


def test_right_count_one_call_and_bad_json_not_retried():
    m = Scripted([arr(3)])
    assert answer_probes(Caller(m, timeout=None), "H", probes(3)) == ["a0", "a1", "a2"]
    assert len(m.calls) == 1
    m = Scripted(["not json at all"])
    out = answer_probes(Caller(m, timeout=None), "H", probes(3))
    assert len(m.calls) == 1 and out[0][1].startswith("answer reply unusable")
    m = Scripted(["nope"])
    res = judge_answers(Caller(m, timeout=None), probes(2), ["a", "b"])
    assert len(m.calls) == 1 and res[0]["error"].startswith("judge reply unusable")


def test_progress_counter_includes_retry():
    buf = io.StringIO()
    m = Scripted([arr(12), arr(11)])
    answer_probes(Caller(m, "s", timeout=None, progress=buf, total=8), "H", probes(11), "checkpoint")
    lines = buf.getvalue().strip().splitlines()
    assert lines[0].startswith("[s] answer (checkpoint) [1/8]")
    assert "[2/9]" in lines[1] and "retry" in lines[1]


def test_wellformed_runs_unchanged_with_fake_model():
    sc = load_scenario(ROOT / "datasets" / "handover-v1" / "coding-20.json")
    buf = io.StringIO()
    res = run_scenario(sc, FakeModel(), progress=buf)
    assert buf.getvalue().count("/8]") == 8 and "retry" not in buf.getvalue()
