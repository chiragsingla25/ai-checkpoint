"""Markdown table and file output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .pipeline import VARIANTS


def _pct(v):
    return "n/a" if v is None else f"{v * 100:.0f}%"


def _num(v):
    return "n/a" if v is None else str(v)


def markdown_table(results: Dict[str, Any]) -> str:
    lines = [
        f"Scenario: {results['scenario']} | model: {results['model']} | "
        f"{results['messages']} messages, {results['probe_count']} probes",
        "",
        "| variant | status | key-fact recall | contradictions | verbatim exact | stale-fact use | next-step acc | brief tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in VARIANTS:
        v = results["variants"][name]
        a = v["aggregate"]
        status = "ok" if v["status"] == "ok" else f"failed: {v['error']}".replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {name} | {status} | {_pct(a['key_fact_recall'])} | {_num(a['contradictions'])} | "
            f"{_pct(a.get('verbatim_exact_match'))} | {_pct(a.get('stale_fact_use'))} | "
            f"{_pct(a.get('next_step_accuracy'))} | {_num(a['brief_tokens'])} |"
        )
    wc = results.get("workspace_capture")
    if wc:
        leak = wc.get("secret_leakage")
        flag = "n/a" if leak is None else ("LEAK (%d)" % leak if leak else "0")
        lines += [
            "",
            "Workspace capture (checkpoint variant, scored by code against the manifest; secret leakage is measured on the model's checkpoint before the product's save-time redaction):",
            "",
            "| capture recall | recall still-relevant | recall done-with | capture precision | status accuracy | secret leakage (distinct secrets, before save-time redaction) |",
            "|---|---|---|---|---|---|",
            f"| {_pct(wc['capture_recall'])} | {_pct(wc.get('recall_still_relevant'))} | "
            f"{_pct(wc.get('recall_done_with'))} | {_pct(wc['capture_precision'])} | "
            f"{_pct(wc['status_accuracy'])} | {flag} |",
        ]
    return "\n".join(lines) + "\n"


def write_outputs(results: Dict[str, Any], out_dir) -> Dict[str, Path]:
    """Write results.json, results.md and handover_<variant>.md; returns the paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    handovers = results.get("_handovers", {})
    public = {k: v for k, v in results.items() if not k.startswith("_")}
    paths = {"json": out / "results.json", "markdown": out / "results.md"}
    paths["json"].write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(markdown_table(results), encoding="utf-8")
    if results.get("_checkpoint") is not None:
        paths["checkpoint"] = out / "checkpoint.json"
        paths["checkpoint"].write_text(json.dumps(results["_checkpoint"], indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    for name, text in handovers.items():
        if text is not None:
            p = out / f"handover_{name}.md"
            p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
            paths[f"handover_{name}"] = p
    return paths
