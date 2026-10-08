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


# ------------------------------------------------------------------ F-001: fixed scorers
FIX = ROOT / "tests" / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_stale_real_answers_now_score_zero():
    rows = _load("real_stale_answers.json")
    assert len(rows) == 17
    for r in rows:
        assert stale_fact_use(r["answer"], r["old"], r["new"]) == 0, (r["scenario"], r["variant"], r["answer"])
    flagged = {(r["scenario"], r["variant"]) for r in rows if r["recorded_stale_fact_use"] == 1}
    for key in [("coding-100", "full_history"), ("coding-100", "checkpoint"), ("coding-20", "summary"),
                ("coding-20", "full_history"), ("data_analysis-100", "checkpoint"),
                ("data_analysis-50", "summary"), ("data_analysis-20", "full_history")]:
        assert key in flagged  # these were the false positives in the real run


def test_stale_old_value_is_the_answer():
    assert stale_fact_use("24 hours.", "24 hours", "48 hours") == 1
    assert stale_fact_use("Rows are kept for 24 hours, not 48 hours.", "24 hours", "48 hours") == 1
    assert stale_fact_use("51,896 customers.", "51,896", "51,225") == 1
    assert stale_fact_use("It is 24 hours, and the cleanup job runs nightly.", "24 hours", "48 hours") == 1
    assert stale_fact_use("The population is 51,896 customers; rows are in data/features.parquet", "51,896", "51,225") == 1


def test_stale_absent_or_history_only():
    assert stale_fact_use("48 hours.", "24 hours", "48 hours") == 0
    assert stale_fact_use("I don't know.", "24 hours", "48 hours") == 0
    assert stale_fact_use("The original 24 hours was replaced by 48 hours.", "24 hours", "48 hours") == 0
    assert stale_fact_use("24 hours was wrong; it is 48 hours.", "24 hours", "48 hours") == 0
    assert stale_fact_use("48 hours (previously 24 hours).", "24 hours", "48 hours") == 0
    assert stale_fact_use("The earlier figure of 51,896 is superseded; use 51,225.", "51,896", "51,225") == 0


def test_next_step_lenient_real_answer_and_filename_forms():
    terms = ["0023_add_event_dedupe.sql", "staging", "replay"]
    cp20 = ("Next, check whether migrations/ exists; 0023 was proposed but not confirmed. Then write the migration "
            "creating webhook_events, apply it to staging once the user confirms, and add the replay test.")
    assert next_step_correct(cp20, terms) == 1
    assert next_step_correct(cp20, terms, strict=True) == 0
    tail = " apply on staging and add the replay test"
    for ok in ("migration 0023", "add_event_dedupe", "MIGRATIONS/0023_ADD_EVENT_DEDUPE.SQL"):
        assert next_step_correct(ok + tail, terms) == 1, ok
    for bad in ("migration 0029", "file 00230", "file 10023"):
        assert next_step_correct(bad + tail, terms) == 0, bad
    assert next_step_correct("Write 0023_add_event_dedupe.sql on staging, replay test", terms, strict=True) == 1


def test_next_step_real_answers():
    rows = _load("real_next_step_answers.json")
    got = {(r["scenario"], r["variant"]): next_step_correct(r["answer"], r["required_terms"]) for r in rows}
    assert got[("coding-20", "checkpoint")] == 1
    for key in [("coding-20", "summary"), ("coding-50", "summary"), ("data_analysis-100", "checkpoint"),
                ("data_analysis-100", "summary"), ("data_analysis-20", "summary")]:
        assert got[key] == 0, key
    for r in rows:  # every other answer keeps its recorded score
        if (r["scenario"], r["variant"]) != ("coding-20", "checkpoint"):
            assert got[(r["scenario"], r["variant"])] == r["recorded_next_step_accuracy"]
    strict = next(r for r in rows if (r["scenario"], r["variant"]) == ("coding-20", "checkpoint"))
    assert next_step_correct(strict["answer"], strict["required_terms"], strict=True) == 0
    key = {"next_step": {"required_terms": ["logistic", "slide"]}}
    assert score_probe("next_step", "next_step", {"next_step": {"required_terms": ["0023_a.sql"]}}, "0023", strict_next_step=True)["next_step_accuracy"] == 0


def test_workspace_path_suffix_matching():
    def rec(m, w, cat="files", wcat="files"):
        return capture_scores({cat: [{"path": m, "status": "still_relevant"}]},
                              {wcat: [{"path": w, "status": "still_relevant"}]}, [])["capture_recall"]
    assert rec("data/raw/", "~/work/retention-study/data/raw/") == 1
    assert rec("data/raw", "$HOME/work/retention-study/data/raw") == 1
    assert rec("raw/x", "data/raw") == 0
    assert rec("data/raw", "~/mydata/raw") == 0
    assert rec("data/raw", "~/work/data/raw2") == 0


def test_workspace_cross_category_recall_and_status():
    m = {"access": [{"path": "~/work/retention-study", "status": "still_relevant"}]}
    ws = {"repos": [{"path": "~/work/retention-study", "status": "still_relevant"}]}
    r = capture_scores(m, ws, [])
    assert r["capture_recall"] == 1 and r["matched"] == 1
    # also files <-> repos
    assert capture_scores({"files": [{"path": "~/w/p", "status": "done_with"}]},
                          {"repos": [{"path": "~/w/p", "status": "done_with"}]}, [])["capture_recall"] == 1
    # other categories stay within themselves
    for cat in ("tools", "connectors", "env_vars", "skills", "references"):
        assert capture_scores({cat: [{"name": "x", "status": "done_with"}]},
                              {"tools" if cat != "tools" else "skills": [{"name": "x", "status": "done_with"}]}, [])["capture_recall"] == 0
    # wrong status on a same-category match lowers status_accuracy
    m2 = {"files": [{"path": "a", "status": "still_relevant"}, {"path": "b", "status": "done_with"}]}
    w2 = {"files": [{"path": "a", "status": "still_relevant"}, {"path": "b", "status": "still_relevant"}]}
    assert capture_scores(m2, w2, [])["status_accuracy"] == 0.5


def test_recall_split_by_status_real_data_analysis_50():
    scenario = json.loads((FIX / "rescore" / "datasets" / "data_analysis-50.json").read_text(encoding="utf-8"))
    ws = _load("data_analysis-50.set_up_first_workspace.json")
    r = capture_scores(scenario["environment"], ws, scenario["secret_values"])
    assert r["recall_still_relevant"] == round(11 / 13, 4) == 0.8462
    assert r["recall_done_with"] == 0.0
    # nothing of a status in the manifest -> None
    only = capture_scores({"files": [{"path": "a", "status": "done_with"}]}, {}, [])
    assert only["recall_still_relevant"] is None and only["recall_done_with"] == 0.0
    # the parser reproduces the transcribed fixture from the saved brief
    from ai_checkpoint.eval.metrics import workspace_from_brief
    brief = (FIX / "rescore" / "results" / "data_analysis-50" / "handover_checkpoint.md").read_text(encoding="utf-8")
    assert workspace_from_brief(brief) == ws


def test_stale_old_value_asserted_as_current_despite_new_mentioned():
    """Attempt 2: the scorer decides which value the answer asserts; negated or history mentions don't count."""
    cases = [
        ("Not 48 hours: rows are kept for 24 hours.", 1),
        ("The handover says 48 hours, but the cleanup SQL uses interval '24 hours', so rows are kept for 24 hours.", 1),
        ("48 hours was considered, but the answer is 24 hours.", 1),
        ("Previously I thought 48 hours, but it is 24 hours.", 1),
        ("24 hours. The handover's updated value of 48 hours is wrong.", 1),
        ("It is 24 hours; some notes say 48 hours but that is outdated.", 1),
        ("Use 24 hours (the 48 hours figure was a draft).", 1),
        ("The current retention is 24 hours. 48 hours was proposed earlier.", 1),
        ("24 hours, not 48.", 1),
        ("Not 24 hours: rows are kept for 48 hours.", 0),
        ("48 hours, not 24 hours.", 0),
        ("24 hours was wrong; it is 48 hours.", 0),
        ("48 hours (previously 24 hours).", 0),
        ("The cleanup SQL says 24 hours, so use 48 hours instead.", 0),
    ]
    for ans, want in cases:
        assert stale_fact_use(ans, "24 hours", "48 hours") == want, ans
    nums = [("Although 51,225 appears in the notes, the final count is 51,896 customers.", 1),
            ("The current figure is 51,896 customers, updated from 51,225.", 1),
            ("The earlier figure of 51,896 is superseded; use 51,225.", 0)]
    for ans, want in nums:
        assert stale_fact_use(ans, "51,896", "51,225") == want, ans
