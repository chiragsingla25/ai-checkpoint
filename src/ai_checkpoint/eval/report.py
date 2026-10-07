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
        "| variant | status | key-fact recall | contradictions | brief tokens |",
        "|---|---|---|---|---|",
    ]
    for name in VARIANTS:
        v = results["variants"][name]
        a = v["aggregate"]
        status = "ok" if v["status"] == "ok" else f"failed: {v['error']}".replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {name} | {status} | {_pct(a['key_fact_recall'])} | {_num(a['contradictions'])} | {_num(a['brief_tokens'])} |"
        )
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
    for name, text in handovers.items():
        if text is not None:
            p = out / f"handover_{name}.md"
            p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
            paths[f"handover_{name}"] = p
    return paths
