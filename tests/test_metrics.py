"""F-003: code-scored metrics and workspace capture scoring."""
import glob
import io
import json
import subprocess
from pathlib import Path

import pytest

from ai_checkpoint.eval.metrics import (capture_scores, next_step_correct, score_probe, stale_fact_use,
                                        verbatim_exact_match)
from ai_checkpoint.eval.models import FakeModel
from ai_checkpoint.eval.pipeline import run_scenario
from ai_checkpoint.eval.report import markdown_table
from ai_checkpoint.eval.scenario import load_scenario
from ai_checkpoint.model import Checkpoint

ROOT = Path(__file__).resolve().parent.parent
DATASET = sorted(glob.glob(str(ROOT / "datasets" / "handover-v1" / "*.json")))


class Counting:
    name = "fake"

    def __init__(self):
        self.inner, self.calls = FakeModel(), 0

    def complete(self, system, messages):
        self.calls += 1
        return self.inner.complete(system, messages)


def test_verbatim_exact_match():
    assert verbatim_exact_match("run pytest -q -k sync", "pytest -q -k sync") == 1
    assert verbatim_exact_match("run pytest -k sync -q", "pytest -q -k sync") == 0
    assert verbatim_exact_match("the value is 0.873", "0.8732") == 0
    assert verbatim_exact_match("  pytest -q  \n", " pytest -q") == 1
    assert verbatim_exact_match("PYTEST -Q", "pytest -q") == 0


def test_verbatim_respects_token_boundaries():
    assert verbatim_exact_match("tolerance is 8680", "868") == 0
    assert verbatim_exact_match("tolerance is 1868", "868") == 0
    assert verbatim_exact_match("tolerance is 868.", "868") == 1
    assert verbatim_exact_match("values 868, 900", "868") == 1
    assert verbatim_exact_match("tolerance is 868", "868") == 1
    assert verbatim_exact_match("rate 0.8732", "0.873") == 0
    assert verbatim_exact_match("rate 0.873.", "0.873") == 1
    assert verbatim_exact_match("n = 1,868", "868") == 0
    assert verbatim_exact_match("INSERT ... NOTHING;", "INSERT ... NOTHING;") == 1


def test_stale_fact_use():
    assert stale_fact_use("we keep rows 24 hours", "24 hours", "72 hours") == 1
    assert stale_fact_use("we keep rows 72 hours", "24 hours", "72 hours") == 0
    assert stale_fact_use("limit is 500", "50", "100") == 0
    assert stale_fact_use("limit is 50 now", "50", "100") == 1
    assert stale_fact_use("rate is 1.50", "1.5", "2") == 0
    assert stale_fact_use("size 51,896 rows", "51,896", "51,225") == 1
    # old is contained in new: only counts when it appears on its own
    assert stale_fact_use("keep 120 days", "20 days", "120 days") == 0


def test_next_step_accuracy_terms():
    terms = ["0023_add_event_dedupe.sql", "staging", "replay"]
    assert next_step_correct("Write 0023_add_event_dedupe.sql, apply on Staging, add the replay test", terms) == 1
    assert next_step_correct("Write 0023_add_event_dedupe.sql and apply on staging", terms) == 0
    key = {"next_step": {"required_terms": terms}, "verbatim": [{"text": "x"}], "correction": {"old": "1", "new": "2"}}
    probes = [("next_step", "next_step", "migration 0023_add_event_dedupe.sql staging replay"),
              ("next_step", "next_step", "something else")]
    vals = [score_probe(k, t, key, a)["next_step_accuracy"] for k, t, a in probes]
    assert sum(vals) / len(vals) == 0.5


def test_probe_scores_null_without_kind_or_key():
    assert score_probe("", "", None, "x") == {"verbatim_exact_match": None, "stale_fact_use": None, "next_step_accuracy": None}
    assert score_probe("verbatim", "verbatim[9]", {"verbatim": []}, "x")["verbatim_exact_match"] is None
    assert score_probe("verbatim", "verbatim[0]", {"verbatim": [{"text": "a"}]}, None)["verbatim_exact_match"] is None


def test_capture_recall_precision_status_example():
    manifest = {"files": [{"path": "a.py", "status": "still_relevant"}, {"path": "b.py", "status": "done_with"},
                          {"path": "notes/", "status": "still_relevant"}],
                "env_vars": [{"name": "TOKEN_X", "status": "still_relevant"}]}
    ws = {"files": [{"path": "a.py", "status": "still_relevant"}, {"path": "b.py", "status": "still_relevant"},
                    {"path": "extra.py", "status": "still_relevant"}]}
    r = capture_scores(manifest, ws, [])
    assert r["capture_recall"] == 0.5
    assert r["capture_precision"] == pytest.approx(0.6667, abs=1e-4)
    assert r["status_accuracy"] == 0.5
    assert r["secret_leakage"] == 0


def test_capture_key_normalisation():
    manifest = {"access": [{"path": "~/work/x/", "status": "still_relevant"}], "files": [{"path": "src/a.py", "status": "done_with"}]}
    ws = {"access": [{"path": "$HOME/work/x", "status": "still_relevant"}], "files": [{"path": "./src/a.py/", "status": "done_with"}]}
    r = capture_scores(manifest, ws, [])
    assert (r["capture_recall"], r["capture_precision"], r["status_accuracy"]) == (1.0, 1.0, 1.0)
    # same key in a different category does not match
    assert capture_scores({"files": [{"path": "a", "status": "done_with"}]}, {"tools": [{"name": "a", "status": "done_with"}]}, [])["capture_recall"] == 0


def test_empty_or_missing_workspace():
    for ws in (None, {}, {"files": []}):
        r = capture_scores({"files": [{"path": "a", "status": "done_with"}]}, ws, ["sk-fake-1"])
        assert r["capture_recall"] == 0 and r["capture_precision"] is None
        assert r["status_accuracy"] is None and r["secret_leakage"] == 0


def test_secret_leakage_counts_everywhere():
    secret = "sk-fake-abc123"
    ws = {"env_vars": [{"name": secret, "status": "still_relevant"}]}
    assert capture_scores({}, ws, [secret])["secret_leakage"] == 1
    # distinct secrets, not occurrences
    assert capture_scores({}, {}, [secret], ["brief mentions sk-fake-abc123", f"json {secret} {secret}"])["secret_leakage"] == 1
    assert capture_scores({}, {}, [secret, "sk-fake-other"], [f"{secret} sk-fake-other"])["secret_leakage"] == 2


class LeakyModel(FakeModel):
    """Puts the secret into the checkpoint's env_vars name."""
    def _compact(self, transcript):
        d = json.loads(super()._compact(transcript))
        d["workspace"]["env_vars"] = [{"name": "sk-fake-leaked", "status": "still_relevant"}]
        return json.dumps(d)


def test_leak_flagged_in_results_md():
    sc = load_scenario(DATASET[0])
    sc.secret_values = ["sk-fake-leaked"]
    res = run_scenario(sc, LeakyModel())
    assert res["workspace_capture"]["secret_leakage"] == 1
    md = markdown_table(res)
    assert "LEAK (1)" in md and "before the product's save-time redaction" in md


def test_old_scenarios_report_na_not_zero():
    for f in glob.glob(str(ROOT / "examples" / "scenarios" / "*.json")):
        sc = load_scenario(f)
        c = Counting()
        res = run_scenario(sc, c)
        assert c.calls == 8
        assert "workspace_capture" not in res
        for v in res["variants"].values():
            a = v["aggregate"]
            assert a["verbatim_exact_match"] is None and a["stale_fact_use"] is None and a["next_step_accuracy"] is None
        md = markdown_table(res)
        assert "n/a" in md and "Workspace capture" not in md


@pytest.mark.parametrize("path", DATASET)
def test_dataset_metrics_and_capture_offline(path):
    sc = load_scenario(path)
    c = Counting()
    res = run_scenario(sc, c)
    assert c.calls == 8
    wc = res["workspace_capture"]
    assert wc["capture_recall"] > 0 and wc["secret_leakage"] == 0 and wc["status"] == "ok"
    for v in res["variants"].values():
        a = v["aggregate"]
        for k in ("verbatim_exact_match", "stale_fact_use", "next_step_accuracy"):
            assert a[k] is not None and 0 <= a[k] <= 1
    md = markdown_table(res)
    assert "verbatim exact" in md and "capture recall" in md and "LEAK" not in md


def test_fake_compaction_workspace_validates_and_has_no_secret_values():
    from ai_checkpoint.eval.pipeline import render_transcript
    for path in DATASET:
        sc = load_scenario(path)
        raw = FakeModel().complete("TASK: COMPACT\n", [{"role": "user", "content": render_transcript(sc.messages)}])
        cp = Checkpoint.from_dict(json.loads(raw))
        assert any(cp.workspace.values())
        assert not any(s in raw for s in sc.secret_values)


def test_suite_48_calls_end_to_end(tmp_path, capsys):
    from ai_checkpoint.eval.cli import main
    rc = main(["suite", *DATASET, "--model", "fake", "--out", str(tmp_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert sum(1 for l in err.splitlines() if "[8/8]" in l) == 6
    files = sorted(tmp_path.glob("*/results.json"))
    assert len(files) == 6
    for f in files:
        d = json.loads(f.read_text())
        assert "workspace_capture" in d and d["workspace_capture"]["secret_leakage"] == 0
        assert "verbatim_exact_match" in d["variants"]["checkpoint"]["aggregate"]


def test_product_code_unchanged():
    """Only product code is checked: src/ai_checkpoint outside eval/. Run folders, tests and
    datasets (tracked or not) are ignored."""
    r = subprocess.run(["git", "status", "--porcelain", "--", "src/ai_checkpoint"], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("no git")
    changed = [l[3:].strip() for l in r.stdout.splitlines()]
    bad = [p for p in changed if not p.startswith("src/ai_checkpoint/eval/")]
    assert bad == [], bad
