"""checkpoint-eval --workers N: bounded parallelism with output identical to a sequential run."""
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from ai_checkpoint.eval import FakeModel, pipeline
from ai_checkpoint.eval import cli as eval_cli
from ai_checkpoint.eval.cli import build_parser, main

ROOT = Path(__file__).resolve().parent.parent
DATASET = sorted(str(p) for p in (ROOT / "datasets" / "handover-v1").glob("*.json"))
PROGRESS = re.compile(r"^\[([\w.-]+)\] (compact|summarize|answer|judge)( \([\w_]+\))? \[(\d+)/8\] [\d.]+s"
                      r"( \(after retry\)| FAILED after 2 attempts \((timeout|error)\))?$")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted in a test")
    monkeypatch.setattr(socket.socket, "connect", boom)
    for var in ("CHECKPOINT_EVAL_FAKE_DELAY", "CHECKPOINT_EVAL_FAKE_FAIL_FIRST"):
        monkeypatch.delenv(var, raising=False)


def tree(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def run_cli(capsys, *argv):
    rc = main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.mark.parametrize("cmd", ["run", "suite"])
def test_help_lists_workers_default_8(cmd):
    text = build_parser().parse_args([cmd, "x.json", "--out", "o"]).workers
    assert text == 8
    sub = build_parser()._subparsers._group_actions[0].choices[cmd]
    assert "--workers" in sub.format_help() and "default 8" in sub.format_help()


@pytest.mark.parametrize("cmd", ["run", "suite"])
@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_bad_workers_exit_2_and_no_output(cmd, bad, tmp_path, capsys):
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as e:
        main([cmd, DATASET[0], "--workers", bad, "--out", str(out)])
    assert e.value.code == 2
    assert "--workers" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("n", [2, 3, 8])
def test_suite_output_identical_to_sequential(n, tmp_path, capsys):
    a, b = tmp_path / "A", tmp_path / "B"
    rc1, out1, err1 = run_cli(capsys, "suite", *DATASET, "--workers", "1", "--out", str(a))
    rc2, out2, err2 = run_cli(capsys, "suite", *DATASET, "--workers", str(n), "--out", str(b))
    assert rc1 == rc2 == 0
    assert out1 == out2 and out1.count("Scenario: ") == len(DATASET)
    ta, tb = tree(a), tree(b)
    assert ta == tb and len(ta) > len(DATASET) * 3
    assert len(err1.splitlines()) == len(err2.splitlines()) == 8 * len(DATASET)


def test_stdout_follows_command_line_order(tmp_path, capsys):
    files = list(reversed(DATASET))
    _, o1, _ = run_cli(capsys, "suite", *files, "--workers", "1", "--out", str(tmp_path / "A"))
    _, o8, _ = run_cli(capsys, "suite", *files, "--workers", "8", "--out", str(tmp_path / "B"))
    assert o1 == o8


def test_run_single_scenario_identical(tmp_path, capsys):
    for n in ("2", "8"):
        run_cli(capsys, "run", DATASET[0], "--workers", "1", "--out", str(tmp_path / "A"), "--force")
        _, o1, _ = run_cli(capsys, "run", DATASET[0], "--workers", "1", "--out", str(tmp_path / "A"), "--force")
        _, o2, _ = run_cli(capsys, "run", DATASET[0], "--workers", n, "--out", str(tmp_path / "B"), "--force")
        assert o1 == o2 and tree(tmp_path / "A") == tree(tmp_path / "B")


class Counting(FakeModel):
    def __init__(self):
        self.lock = threading.Lock()
        self.now = self.peak = 0

    def complete(self, system, messages):
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
        try:
            return super().complete(system, messages)
        finally:
            with self.lock:
                self.now -= 1


@pytest.mark.parametrize("n", [1, 2, 3, 8])
def test_in_flight_cap(n, tmp_path, monkeypatch, capsys):
    model = Counting()
    monkeypatch.setattr(eval_cli, "make_model", lambda *a, **k: model)
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_DELAY", "0.03")
    rc, _, _ = run_cli(capsys, "suite", *DATASET, "--workers", str(n), "--out", str(tmp_path / "o"))
    assert rc == 0
    assert model.peak <= n
    if n > 1:
        assert model.peak == n


def test_within_scenario_ordering(tmp_path, monkeypatch, capsys):
    events = []
    orig = pipeline.Caller.call

    def rec(self, stage, system, messages, detail=""):
        t0 = time.monotonic()
        try:
            return orig(self, stage, system, messages, detail)
        finally:
            events.append((stage, detail, t0, time.monotonic()))

    monkeypatch.setattr(pipeline.Caller, "call", rec)
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_DELAY", "0.15")
    rc, _, _ = run_cli(capsys, "run", DATASET[0], "--workers", "8", "--out", str(tmp_path / "o"))
    assert rc == 0
    ev = {(s, d): (a, b) for s, d, a, b in events}
    assert len(ev) == 8
    c, s = ev[("compact", "")], ev[("summarize", "")]
    assert c[0] < s[1] and s[0] < c[1]  # overlap
    fa = ev[("answer", "full_history")]
    assert fa[0] < min(c[1], s[1])
    for v in ("checkpoint", "summary", "full_history"):
        assert ev[("judge", v)][0] >= ev[("answer", v)][1]
    # full_history's judge does not wait for the other variants
    assert ev[("judge", "full_history")][0] < ev[("answer", "checkpoint")][1]


def test_progress_lines_whole_and_counted(tmp_path, capsys):
    _, _, e1 = run_cli(capsys, "suite", *DATASET, "--workers", "1", "--out", str(tmp_path / "A"))
    _, _, e8 = run_cli(capsys, "suite", *DATASET, "--workers", "8", "--out", str(tmp_path / "B"))
    lines = e8.splitlines()
    assert len(lines) == len(e1.splitlines()) == 48
    seen = {}
    for ln in lines:
        m = PROGRESS.match(ln)
        assert m, ln
        seen.setdefault(m.group(1), []).append(int(m.group(4)))
    assert len(seen) == len(DATASET)
    for ks in seen.values():
        assert ks == list(range(1, 9))  # counters assigned in finishing order


def test_parallel_is_faster(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_DELAY", "0.05")
    t = {}
    for n in (1, 8):
        t0 = time.monotonic()
        rc, _, _ = run_cli(capsys, "suite", *DATASET, "--workers", str(n), "--out", str(tmp_path / f"o{n}"))
        assert rc == 0
        t[n] = time.monotonic() - t0
    assert t[1] > 48 * 0.05 * 0.9
    assert t[8] < t[1] / 2


def test_retry_per_call_under_workers(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_FAIL_FIRST", "1")
    rc1, o1, e1 = run_cli(capsys, "suite", *DATASET, "--workers", "1", "--out", str(tmp_path / "A"))
    rc8, o8, e8 = run_cli(capsys, "suite", *DATASET, "--workers", "8", "--out", str(tmp_path / "B"))
    assert rc1 == rc8 == 0 and o1 == o8 and tree(tmp_path / "A") == tree(tmp_path / "B")
    assert e8.count("(after retry)") == e1.count("(after retry)") == 48


def test_timeout_per_call_under_workers(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHECKPOINT_EVAL_FAKE_DELAY", "0.4")
    rc, out, err = run_cli(capsys, "suite", *DATASET[:2], "--workers", "8", "--timeout", "0.1",
                           "--out", str(tmp_path / "o"))
    assert rc == 1 and out == ""
    for p in DATASET[:2]:
        name = Path(p).stem
        assert f"error: scenario {name}:" in err
    assert err.count("FAILED after 2 attempts (timeout)") >= 2


def test_failure_isolation(tmp_path, capsys):
    clean = tmp_path / "clean"
    run_cli(capsys, "suite", *DATASET, "--workers", "1", "--out", str(clean))
    bad = Path(DATASET[2]).stem
    out = tmp_path / "bad"
    out.mkdir()
    (out / bad).write_text("not a directory")
    rc, stdout, err = run_cli(capsys, "suite", *DATASET, "--workers", "8", "--out", str(out))
    assert rc == 1
    assert f"error: scenario {bad}:" in err
    names = [Path(p).stem for p in DATASET if Path(p).stem != bad]
    got = tree(out)
    want = tree(clean)
    for n in names:
        assert {k: v for k, v in got.items() if k.startswith(n + "/")} == \
               {k: v for k, v in want.items() if k.startswith(n + "/")}
    order = re.findall(r"^Scenario: (\S+)", stdout, flags=re.M)
    assert order == names
