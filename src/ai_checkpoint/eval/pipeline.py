"""Build the three handover variants, answer probes in fresh calls, judge the answers."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..brief import estimate_tokens, render_brief
from ..errors import ValidationError
from ..model import Checkpoint
from ..schema import compaction_system_prompt
from .models import TASK_ANSWER, TASK_JUDGE, TASK_SUMMARIZE, Model
from .scenario import Probe, Scenario

VARIANTS = ("checkpoint", "summary", "full_history")

SUMMARY_SYSTEM = (
    f"{TASK_SUMMARIZE}\n\n"
    "Summarize the conversation you are given so that someone who was not part of it can "
    "continue the work in a new chat. Reply with the summary only."
)

ANSWER_SYSTEM = (
    f"{TASK_ANSWER}\n\n"
    "You are starting a brand-new chat. You have no memory of earlier conversations; the only "
    "knowledge you have about the earlier work is the handover below. Answer the user's question "
    "using only the handover. If the handover does not contain the answer, say so instead of "
    "guessing. Be specific and give exact values where you have them.\n\n"
    "HANDOVER:\n"
)

JUDGE_SYSTEM = (
    f"{TASK_JUDGE}\n\n"
    "You grade an answer against a reference. The user message is a JSON object with: question, "
    "reference, key_facts (list), must_not_contradict (list of true statements), known_wrong "
    "(list of wrong claims), and answer.\n"
    "1. For each entry of key_facts, in order, decide whether the answer states that fact "
    "(equivalent wording is fine; exact values such as numbers, names and code must match). "
    "Output one boolean per key fact in `present`.\n"
    "2. Count in `contradictions` how many statements in the answer contradict the reference, "
    "the key facts or must_not_contradict, or assert something listed in known_wrong. "
    "Omissions are not contradictions. Do not count the same wrong statement twice.\n"
    'Reply with ONLY a JSON object: {"present": [true|false, ...], "contradictions": <integer>, '
    '"notes": "<one short sentence>"}'
)


def render_transcript(messages: List[dict]) -> str:
    return "\n\n".join(f"=== {m['role']} ===\n{m['content']}" for m in messages)


def extract_json(text: str) -> Any:
    """Parse the JSON object in a model reply, tolerating code fences and surrounding prose."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except ValueError:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("no JSON object found in the reply") from None
        return json.loads(t[a : b + 1])


def _compaction_handover(scenario: Scenario, model: Model) -> str:
    """Compaction call -> validate with the F-001 model -> render the F-002 brief."""
    prompt = (
        "Save a checkpoint of the conversation below. The conversation follows, to the end of "
        "this message; every message is introduced by a line like `=== user ===`.\n\n"
        + render_transcript(scenario.messages)
    )
    raw = model.complete(compaction_system_prompt(), [{"role": "user", "content": prompt}])
    try:
        data = extract_json(raw)
    except (ValueError, RecursionError) as e:
        raise ValidationError("compaction output", f"is not valid JSON ({e})") from None
    cp = Checkpoint.from_dict(data)  # ValidationError names the field
    return render_brief(cp)


def build_handovers(scenario: Scenario, model: Model) -> Dict[str, Dict[str, Any]]:
    """variant -> {"handover": text | None, "error": str | None}."""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        out["checkpoint"] = {"handover": _compaction_handover(scenario, model), "error": None}
    except ValidationError as e:  # recorded, not fatal; model/API failures (ModelError) still abort
        out["checkpoint"] = {"handover": None, "error": str(e)}
    summary = model.complete(
        SUMMARY_SYSTEM, [{"role": "user", "content": render_transcript(scenario.messages)}]
    ).strip()
    if summary:
        out["summary"] = {"handover": "Summary of the previous chat:\n\n" + summary, "error": None}
    else:
        out["summary"] = {"handover": None, "error": "summary model returned an empty reply"}
    out["full_history"] = {
        "handover": "Full transcript of the previous chat:\n\n" + render_transcript(scenario.messages),
        "error": None,
    }
    return out


def answer_probe(model: Model, handover: str, question: str) -> str:
    """A fresh 'new chat' call: only the handover and the question, nothing shared."""
    return model.complete(ANSWER_SYSTEM + handover, [{"role": "user", "content": question}]).strip()


def judge_answer(model: Model, probe: Probe, answer: str) -> Dict[str, Any]:
    payload = json.dumps(
        {
            "question": probe.question,
            "reference": probe.reference,
            "key_facts": probe.key_facts,
            "must_not_contradict": probe.must_not_contradict,
            "known_wrong": probe.known_wrong,
            "answer": answer,
        },
        ensure_ascii=False,
    )
    raw = model.complete(JUDGE_SYSTEM, [{"role": "user", "content": payload}])
    n = len(probe.key_facts)
    try:
        d = extract_json(raw)
        present = d["present"]
        if not isinstance(present, list) or len(present) != n or not all(isinstance(x, bool) for x in present):
            raise ValueError(f"'present' must be a list of {n} booleans")
        contra = d.get("contradictions", 0)
        if isinstance(contra, bool) or not isinstance(contra, int) or contra < 0:
            raise ValueError("'contradictions' must be a non-negative integer")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return {"error": f"judge reply unusable: {e}", "key_fact_recall": None, "contradictions": None,
                "facts": [{"fact": f, "present": None} for f in probe.key_facts]}
    return {
        "key_fact_recall": sum(present) / n,
        "contradictions": contra,
        "facts": [{"fact": f, "present": p} for f, p in zip(probe.key_facts, present)],
        "judge_notes": str(d.get("notes", "")),
        "error": None,
    }


def _aggregate(probes: List[dict], brief_tokens: Optional[int]) -> Dict[str, Any]:
    scored = [p for p in probes if p["key_fact_recall"] is not None]
    return {
        "key_fact_recall": (sum(p["key_fact_recall"] for p in scored) / len(scored)) if scored else None,
        "contradictions": sum(p["contradictions"] for p in scored) if scored else None,
        "brief_tokens": brief_tokens,
        "probes_scored": len(scored),
        "probes_total": len(probes),
    }


def run_scenario(scenario: Scenario, model: Model) -> Dict[str, Any]:
    """Run all variants and probes. Returns the JSON-ready results dict plus handover texts
    under the key ``_handovers`` (not part of the results file; the CLI writes them separately)."""
    handovers = build_handovers(scenario, model)
    variants: Dict[str, Any] = {}
    for name in VARIANTS:
        h = handovers[name]
        if h["handover"] is None:
            variants[name] = {
                "status": "failed", "error": h["error"], "handover_chars": None,
                "probes": [], "aggregate": _aggregate([], None),
            }
            continue
        text = h["handover"]
        probes = []
        for probe in scenario.probes:
            ans = answer_probe(model, text, probe.question)
            probes.append({"question": probe.question, "answer": ans, **judge_answer(model, probe, ans)})
        variants[name] = {
            "status": "ok", "error": None, "handover_chars": len(text),
            "probes": probes, "aggregate": _aggregate(probes, estimate_tokens(text)),
        }
    return {
        "scenario": scenario.name,
        "description": scenario.description,
        "model": model.name,
        "messages": len(scenario.messages),
        "probe_count": len(scenario.probes),
        "variants": variants,
        "_handovers": {k: v["handover"] for k, v in handovers.items()},
    }
