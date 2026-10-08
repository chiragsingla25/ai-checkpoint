"""``checkpoint-eval rescore``: recompute the code-scored metrics of a finished run from the saved
answers, the scenario file and the saved checkpoint (or the brief), with no model call.
results.json and handover_*.md are never modified; each scenario folder gets a rescored.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..errors import CheckpointError
from .metrics import capture_scores, mean_or_none, score_probe, workspace_from_brief
from .pipeline import VARIANTS
from .scenario import load_scenario

METRICS = ("verbatim_exact_match", "stale_fact_use", "next_step_accuracy")
WS_KEYS = ("capture_recall", "recall_still_relevant", "recall_done_with", "capture_precision", "status_accuracy",
           "secret_leakage")


class RescoreError(CheckpointError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise RescoreError(f"cannot read {path}: {e}") from None


def find_results(root: Path) -> List[Path]:
    if not root.exists():
        raise RescoreError(f"results path {root} does not exist")
    if root.is_file():
        raise RescoreError(f"results path {root} is not a folder")
    found = sorted(root.rglob("results.json"))
    if not found:
        raise RescoreError(f"no results.json found under {root}")
    return found


def _workspace(folder: Path, results: dict, scenario) -> tuple:
    """(workspace dict | None, source, texts for secret scan)."""
    brief_path = folder / "handover_checkpoint.md"
    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    cp_path = folder / "checkpoint.json"
    if cp_path.exists():
        cp = _read_json(cp_path)
        ws = cp.get("workspace") if isinstance(cp, dict) else None
        return (ws or {}), "checkpoint.json", [json.dumps(cp, ensure_ascii=False), brief]
    if brief:
        ws = workspace_from_brief(brief)
        if ws is not None:
            return ws, "handover_checkpoint.md ('Set up first' section)", [brief]
    return None, "none", []


def rescore_one(results_path: Path, dataset: Path, strict_next_step: bool) -> Dict[str, Any]:
    folder = results_path.parent
    results = _read_json(results_path)
    name = results.get("scenario") if isinstance(results, dict) else None
    if not name:
        raise RescoreError(f"{results_path} has no 'scenario' name")
    sc_path = dataset / f"{name}.json"
    if not sc_path.exists():
        raise RescoreError(f"scenario {name} not found in {dataset} (looked for {sc_path})")
    scenario = load_scenario(sc_path)
    out: Dict[str, Any] = {"scenario": name, "dataset": str(dataset), "strict_next_step": strict_next_step,
                           "variants": {}}
    for vname, v in (results.get("variants") or {}).items():
        probes = v.get("probes") or []
        if probes and len(probes) != len(scenario.probes):
            raise RescoreError(f"scenario {name}: {len(probes)} saved probes but {len(scenario.probes)} in {sc_path}")
        rows = []
        for pr, p in zip(scenario.probes, probes):
            old = {m: p.get(m) for m in METRICS}
            if p.get("error") or p.get("answer") is None:
                new = {m: None for m in METRICS}
            else:
                new = score_probe(pr.kind, pr.target, scenario.answer_key, p["answer"], strict_next_step)
            rows.append({"question": pr.question, "kind": pr.kind, "old": old, "new": new})
        out["variants"][vname] = {
            "probes": rows,
            "aggregate": {"old": {m: mean_or_none(r["old"][m] for r in rows) for m in METRICS},
                          "new": {m: mean_or_none(r["new"][m] for r in rows) for m in METRICS}},
        }
    old_wc = results.get("workspace_capture")
    if scenario.environment:
        ws, source, texts = _workspace(folder, results, scenario)
        if ws is None:
            out["workspace_capture"] = {"source": source, "old": old_wc, "new": None}
        else:
            new = capture_scores(scenario.environment, ws, scenario.secret_values, texts)
            out["workspace_capture"] = {"source": source, "old": old_wc, "new": new}
    (folder / "rescored.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _pct(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def _pair(d: dict, key: str) -> str:
    return f"{_pct(d['old'].get(key))} -> {_pct(d['new'].get(key))}"


def format_table(r: Dict[str, Any]) -> str:
    lines = [f"Scenario: {r['scenario']}", "",
             "| variant | verbatim exact (old -> new) | stale-fact use (old -> new) | next-step acc (old -> new) |",
             "|---|---|---|---|"]
    for name in VARIANTS:
        v = r["variants"].get(name)
        if v:
            a = v["aggregate"]
            lines.append(f"| {name} | {_pair(a, 'verbatim_exact_match')} | {_pair(a, 'stale_fact_use')} | "
                         f"{_pair(a, 'next_step_accuracy')} |")
    wc = r.get("workspace_capture")
    if wc and wc.get("new"):
        old = wc.get("old") or {}
        lines += ["", f"Workspace capture (source: {wc['source']}):", "",
                  "| metric | old -> new |", "|---|---|"]
        for k in WS_KEYS:
            if k == "secret_leakage":
                lines.append(f"| {k} | {old.get(k, 'n/a')} -> {wc['new'].get(k)} |")
            else:
                lines.append(f"| {k} | {_pct(old.get(k))} -> {_pct(wc['new'].get(k))} |")
    return "\n".join(lines) + "\n"


def rescore_command(results_dir: str, dataset: str, strict_next_step: bool = False) -> int:
    try:
        paths = find_results(Path(results_dir))
    except RescoreError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    failed = 0
    first = True
    for rp in paths:
        try:
            r = rescore_one(rp, Path(dataset), strict_next_step)
        except (CheckpointError, OSError) as e:
            print(f"error: {str(e).splitlines()[0] if str(e) else rp}", file=sys.stderr)
            failed += 1
            continue
        if not first:
            print()
        first = False
        print(format_table(r), end="")
    return 1 if failed else 0
