"""Build the three handover variants, answer probes in fresh calls, judge the answers."""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional, TextIO

from ..brief import estimate_tokens, render_brief
from ..errors import ValidationError
from ..model import Checkpoint
from ..schema import compaction_system_prompt
from .models import (DEFAULT_TIMEOUT, TASK_ANSWER, TASK_JUDGE, TASK_SUMMARIZE, CallTimeout, Model,
                     ModelError, call_with_timeout)
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
    "knowledge you have about the earlier work is the handover below. The user message is a JSON "
    'object {"questions": [...]}. Answer every question using only the handover. If the handover '
    "does not contain an answer, say so instead of guessing. Be specific and give exact values "
    "(numbers, names, commands, code) where you have them.\n"
    "Reply with ONLY a JSON array of strings: one answer per question, in the same order, with "
    "exactly as many entries as there are questions.\n\n"
    "HANDOVER:\n"
)

JUDGE_SYSTEM = (
    f"{TASK_JUDGE}\n\n"
    "You grade answers against references. The user message is a JSON object "
    '{"items": [...]}; each item has: question, reference, key_facts (list), must_not_contradict '
    "(list of true statements), known_wrong (list of wrong claims), and answer. For EACH item:\n"
    "1. For each entry of key_facts, in order, decide whether the answer states that fact "
    "(equivalent wording is fine; exact values such as numbers, names and code must match). "
    "Output one boolean per key fact in `present`.\n"
    "2. Count in `contradictions` how many statements in the answer contradict the reference, "
    "the key facts or must_not_contradict, or assert something listed in known_wrong. "
    "Omissions are not contradictions. Do not count the same wrong statement twice.\n"
    'Reply with ONLY a JSON array with one object per item, in order: '
    '[{"present": [true|false, ...], "contradictions": <integer>, "notes": "<one short sentence>"}, ...]'
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


def extract_json_list(text: str) -> list:
    """Parse the JSON array in a model reply, tolerating code fences and surrounding prose.
    An object holding the array under `answers`/`results` is accepted too."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    dec = json.JSONDecoder()
    tries = 0
    for start in [0] + [k for k, ch in enumerate(t) if ch in "[{"]:
        if tries >= 60:
            break
        tries += 1
        try:
            val, _ = dec.raw_decode(t[start:].lstrip())
        except ValueError:
            continue
        if isinstance(val, dict):
            for key in ("answers", "results"):
                if isinstance(val.get(key), list):
                    return val[key]
            continue
        if isinstance(val, list):
            return val
    raise ValueError("no JSON array found in the reply")


class CallFailed(ModelError):
    """A model call failed on both attempts."""


class Caller:
    """Runs model calls with a per-call timeout, one retry, and a progress line per call."""

    def __init__(self, model: Model, scenario: str = "", timeout: Optional[float] = DEFAULT_TIMEOUT,
                 progress: Optional[TextIO] = None, total: int = 8):
        self.model, self.scenario, self.timeout = model, scenario, timeout
        self.progress, self.total = progress, total
        self.count = 0
        self.t0 = time.monotonic()

    def _say(self, stage: str, detail: str, note: str = "") -> None:
        if self.progress is None:
            return
        label = f"{stage} ({detail})" if detail else stage
        print(f"[{self.scenario}] {label} [{self.count}/{self.total}] {time.monotonic() - self.t0:.1f}s{note}",
              file=self.progress, flush=True)

    def call(self, stage: str, system: str, messages: List[dict], detail: str = "") -> str:
        self.count += 1
        last: Optional[ModelError] = None
        for attempt in (1, 2):
            try:
                out = call_with_timeout(self.model, system, messages, self.timeout)
            except ModelError as e:
                last = e
                continue
            self._say(stage, detail, " (after retry)" if attempt == 2 else "")
            return out
        kind = "timeout" if isinstance(last, CallTimeout) else "error"
        self._say(stage, detail, f" FAILED after 2 attempts ({kind})")
        raise CallFailed(f"{stage} call failed after 2 attempts: {last}") from None


def _compaction_handover(scenario: Scenario, model: Model, caller: Optional[Caller] = None) -> str:
    """Compaction call -> validate with the F-001 model -> render the F-002 brief."""
    prompt = (
        "Save a checkpoint of the conversation below. The conversation follows, to the end of "
        "this message; every message is introduced by a line like `=== user ===`.\n\n"
        + render_transcript(scenario.messages)
    )
    raw = _call(caller, model, "compact", compaction_system_prompt(), [{"role": "user", "content": prompt}])
    try:
        data = extract_json(raw)
    except (ValueError, RecursionError) as e:
        raise ValidationError("compaction output", f"is not valid JSON ({e})") from None
    cp = Checkpoint.from_dict(data)  # ValidationError names the field
    return render_brief(cp)


def _call(caller: Optional[Caller], model: Model, stage: str, system: str, messages: List[dict], detail: str = "") -> str:
    if caller is None:
        return model.complete(system, messages)
    return caller.call(stage, system, messages, detail)


def build_handovers(scenario: Scenario, model: Model, caller: Optional[Caller] = None) -> Dict[str, Dict[str, Any]]:
    """variant -> {"handover": text | None, "error": str | None}."""
    out: Dict[str, Dict[str, Any]] = {}
    try:
        out["checkpoint"] = {"handover": _compaction_handover(scenario, model, caller), "error": None}
    except ValidationError as e:  # recorded, not fatal; model/API failures (ModelError) still abort
        out["checkpoint"] = {"handover": None, "error": str(e)}
    summary = _call(
        caller, model, "summarize", SUMMARY_SYSTEM, [{"role": "user", "content": render_transcript(scenario.messages)}]
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


def _probe_entry(probe: Probe, answer: Optional[str], error: str) -> Dict[str, Any]:
    return {"question": probe.question, "answer": answer, "key_fact_recall": None, "contradictions": None,
            "facts": [{"fact": f, "present": None} for f in probe.key_facts], "error": error}


def answer_probes(caller: Caller, handover: str, probes: List[Probe], detail: str = "") -> List[Any]:
    """ONE fresh 'new chat' call: only the handover and all the questions.
    Returns one entry per probe: the answer text, or an error string wrapped as ("error", msg)."""
    n = len(probes)
    user = json.dumps({"questions": [p.question for p in probes]}, ensure_ascii=False)
    raw = caller.call("answer", ANSWER_SYSTEM + handover, [{"role": "user", "content": user}], detail)
    try:
        items = extract_json_list(raw)
    except (ValueError, RecursionError) as e:
        return [("error", f"answer reply unusable: {e}")] * n
    if len(items) != n:
        return [("error", f"answer reply unusable: expected {n} answers, got {len(items)}")] * n
    out: List[Any] = []
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("answer"), str):
            it = it["answer"]
        out.append(it.strip() if isinstance(it, str) else ("error", "answer reply unusable: entry is not text"))
    return out


def _check_verdict(d: Any, n_facts: int) -> Dict[str, Any]:
    present = d["present"]
    if not isinstance(present, list) or len(present) != n_facts or not all(isinstance(x, bool) for x in present):
        raise ValueError(f"'present' must be a list of {n_facts} booleans")
    contra = d.get("contradictions", 0)
    if isinstance(contra, bool) or not isinstance(contra, int) or contra < 0:
        raise ValueError("'contradictions' must be a non-negative integer")
    return {"present": present, "contradictions": contra, "notes": str(d.get("notes", ""))}


def judge_answers(caller: Caller, probes: List[Probe], answers: List[str], detail: str = "") -> List[Dict[str, Any]]:
    """ONE judge call grading all answers. Returns one result dict per probe (error + null scores
    where the reply is unusable)."""
    n = len(probes)

    def bad(msg: str) -> List[Dict[str, Any]]:
        return [{"error": msg, "key_fact_recall": None, "contradictions": None,
                 "facts": [{"fact": f, "present": None} for f in p.key_facts]} for p in probes]

    payload = json.dumps({"items": [
        {"question": p.question, "reference": p.reference, "key_facts": p.key_facts,
         "must_not_contradict": p.must_not_contradict, "known_wrong": p.known_wrong, "answer": a}
        for p, a in zip(probes, answers)]}, ensure_ascii=False)
    raw = caller.call("judge", JUDGE_SYSTEM, [{"role": "user", "content": payload}], detail)
    try:
        items = extract_json_list(raw)
    except (ValueError, RecursionError) as e:
        return bad(f"judge reply unusable: {e}")
    if len(items) != n:
        return bad(f"judge reply unusable: expected {n} verdicts, got {len(items)}")
    out = []
    for p, d in zip(probes, items):
        try:
            v = _check_verdict(d, len(p.key_facts))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            out.append(bad(f"judge reply unusable: {e}")[0])
            continue
        out.append({
            "key_fact_recall": sum(v["present"]) / len(p.key_facts),
            "contradictions": v["contradictions"],
            "facts": [{"fact": f, "present": x} for f, x in zip(p.key_facts, v["present"])],
            "judge_notes": v["notes"],
            "error": None,
        })
    return out


def judge_answer(model: Model, probe: Probe, answer: str) -> Dict[str, Any]:
    """Grade a single answer (a batch of one)."""
    return judge_answers(Caller(model, timeout=None), [probe], [answer])[0]


def _aggregate(probes: List[dict], brief_tokens: Optional[int]) -> Dict[str, Any]:
    scored = [p for p in probes if p["key_fact_recall"] is not None]
    return {
        "key_fact_recall": (sum(p["key_fact_recall"] for p in scored) / len(scored)) if scored else None,
        "contradictions": sum(p["contradictions"] for p in scored) if scored else None,
        "brief_tokens": brief_tokens,
        "probes_scored": len(scored),
        "probes_total": len(probes),
    }


def run_scenario(scenario: Scenario, model: Model, timeout: Optional[float] = DEFAULT_TIMEOUT,
                 progress: Optional[TextIO] = None) -> Dict[str, Any]:
    """Run all variants and probes with 8 model calls: compaction, summary, then per variant one
    answer call and one judge call. Returns the JSON-ready results dict plus handover texts
    under the key ``_handovers`` (not part of the results file; the CLI writes them separately).
    Compaction/summary failures after the retry raise; answer/judge failures are recorded."""
    caller = Caller(model, scenario.name, timeout, progress, total=2 + 2 * len(VARIANTS))
    handovers = build_handovers(scenario, model, caller)
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
        status, error = "ok", None
        try:
            answers = answer_probes(caller, text, scenario.probes, name)
            good = [i for i, a in enumerate(answers) if isinstance(a, str)]
            verdicts: Dict[int, Dict[str, Any]] = {}
            if good:
                res = judge_answers(caller, [scenario.probes[i] for i in good], [answers[i] for i in good], name)
                verdicts = dict(zip(good, res))
            probes = []
            for i, (pr, a) in enumerate(zip(scenario.probes, answers)):
                if isinstance(a, str):
                    probes.append({"question": pr.question, "answer": a, **verdicts[i]})
                else:
                    probes.append(_probe_entry(pr, None, a[1]))
        except CallFailed as e:
            status, error = "failed", str(e)
            probes = [_probe_entry(pr, None, str(e)) for pr in scenario.probes]
        variants[name] = {
            "status": status, "error": error, "handover_chars": len(text),
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
