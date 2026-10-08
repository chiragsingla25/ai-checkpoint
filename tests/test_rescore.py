"""F-001: `checkpoint-eval rescore` recomputes code-scored metrics from saved results, offline."""
import json
import shutil
from pathlib import Path

import pytest

from ai_checkpoint.eval import cli, models

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "rescore"
DATASET = FIX / "datasets"


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("rescore must not create or call a model")
    monkeypatch.setattr(models, "make_model", boom)
    monkeypatch.setattr(cli, "make_model", boom)
    d = tmp_path / "run"
    shutil.copytree(FIX / "results", d)
    return d


def _snapshot(d):
    return {p.relative_to(d): p.read_bytes() for p in d.rglob("*") if p.is_file() and p.name != "rescored.json"}


def test_rescore_fixture_run(run_dir, capsys):
    before = _snapshot(run_dir)
    assert cli.main(["rescore", str(run_dir), "--dataset", str(DATASET)]) == 0
    assert _snapshot(run_dir) == before  # results.json and handover_*.md untouched
    out = capsys.readouterr().out
    assert "coding-20" in out and "data_analysis-50" in out and "->" in out
    c20 = json.loads((run_dir / "coding-20" / "rescored.json").read_text())
    for vname, v in c20["variants"].items():
        for p in v["probes"]:
            if p["kind"] == "stale":
                assert p["new"]["stale_fact_use"] == 0
    assert c20["variants"]["checkpoint"]["aggregate"]["old"]["next_step_accuracy"] == 0
    assert c20["variants"]["checkpoint"]["aggregate"]["new"]["next_step_accuracy"] == 1
    da = json.loads((run_dir / "data_analysis-50" / "rescored.json").read_text())
    assert da["workspace_capture"]["source"].startswith("handover_checkpoint.md")
    assert da["workspace_capture"]["new"]["recall_still_relevant"] == 0.8462
    for s in ("coding-20", "data_analysis-50", "coding-50"):
        for v in json.loads((run_dir / s / "rescored.json").read_text())["variants"].values():
            for p in v["probes"]:
                if p["kind"] == "stale":
                    assert p["new"]["stale_fact_use"] in (0, None)


def test_rescore_error_probes_stay_null(run_dir):
    assert cli.main(["rescore", str(run_dir), "--dataset", str(DATASET)]) == 0
    c50 = json.loads((run_dir / "coding-50" / "rescored.json").read_text())
    probes = c50["variants"]["checkpoint"]["probes"]
    assert probes and all(p["new"][m] is None for p in probes for m in p["new"])
    stale = [p for p in c50["variants"]["full_history"]["probes"] if p["kind"] == "stale"]
    assert stale and stale[0]["new"]["stale_fact_use"] == 0


def test_rescore_prefers_checkpoint_json_and_strict_flag(run_dir):
    cp = {"workspace": {"repos": [{"path": "~/work/retention-study", "status": "still_relevant"}]}}
    (run_dir / "data_analysis-50" / "checkpoint.json").write_text(json.dumps(cp))
    assert cli.main(["rescore", str(run_dir), "--dataset", str(DATASET), "--strict-next-step"]) == 0
    da = json.loads((run_dir / "data_analysis-50" / "rescored.json").read_text())
    assert da["workspace_capture"]["source"] == "checkpoint.json"
    assert da["workspace_capture"]["new"]["workspace_items"] == 1
    c20 = json.loads((run_dir / "coding-20" / "rescored.json").read_text())
    assert c20["variants"]["checkpoint"]["aggregate"]["new"]["next_step_accuracy"] == 0  # strict


def test_rescore_failures(run_dir, tmp_path, capsys):
    assert cli.main(["rescore", str(tmp_path / "nope"), "--dataset", str(DATASET)]) == 1
    assert str(tmp_path / "nope") in capsys.readouterr().err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["rescore", str(empty), "--dataset", str(DATASET)]) == 1
    err = capsys.readouterr().err
    assert str(empty) in err and len(err.strip().splitlines()) == 1
    # one scenario missing from the dataset: others still rescored, exit non-zero
    partial = tmp_path / "partial"
    shutil.copytree(DATASET, partial)
    (partial / "coding-20.json").unlink()
    assert cli.main(["rescore", str(run_dir), "--dataset", str(partial)]) == 1
    err = capsys.readouterr().err
    assert "coding-20" in err and len(err.strip().splitlines()) == 1
    assert not (run_dir / "coding-20" / "rescored.json").exists()
    assert (run_dir / "data_analysis-50" / "rescored.json").exists()


def test_new_runs_save_checkpoint_json(tmp_path):
    from ai_checkpoint.eval.models import FakeModel
    from ai_checkpoint.eval.pipeline import run_scenario
    from ai_checkpoint.eval.report import write_outputs, markdown_table
    from ai_checkpoint.eval.scenario import load_scenario
    sc = load_scenario(next((ROOT / "datasets" / "handover-v1").glob("data_analysis-20.json")))
    res = run_scenario(sc, FakeModel())
    paths = write_outputs(res, tmp_path / "o")
    cp = json.loads(paths["checkpoint"].read_text())
    assert "workspace" in cp and "objective" in cp
    assert "_checkpoint" not in json.loads(paths["json"].read_text())
    assert "recall still-relevant" in markdown_table(res)
