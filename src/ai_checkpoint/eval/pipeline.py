"""Build the three handover variants, answer probes in fresh calls, judge the answers."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from ..brief import estimate_tokens, render_brief
from ..errors import ValidationError
from ..model import Checkpoint
from ..schema import compaction_system_prompt
from ..store import GitStore
from .models import (DEFAULT_TIMEOUT, TASK_ANSWER, TASK_JUDGE, TASK_SUMMARIZE, CallTimeout, Model,
                     ModelError, call_with_timeout)
from .metrics import capture_scores, mean_or_none, score_probe
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


# one lock for progress lines and counters, shared by every Caller so lines never interleave
_PROGRESS_LOCK = threading.Lock()


class CallFailed(ModelError):
    """A model call failed on both attempts."""


class Caller:
    """Runs model calls with a per-call timeout, one retry, and a progress line per call."""

    def __init__(self, model: Model, scenario: str = "", timeout: Optional[float] = DEFAULT_TIMEOUT,
                 progress: Optional[TextIO] = None, total: int = 8, limiter: Optional[Any] = None):
        self.model, self.scenario, self.timeout = model, scenario, timeout
        self.limiter = limiter  # semaphore shared across scenarios: caps in-flight model calls
        self.progress, self.total = progress, total
        self.count = 0
        self.t0 = time.monotonic()

    def _say(self, stage: str, detail: str, note: str = "") -> None:
        """Count one finished call and print its progress line (atomically)."""
        with _PROGRESS_LOCK:
            self.count += 1
            if self.progress is None:
                return
            label = f"{stage} ({detail})" if detail else stage
            print(f"[{self.scenario}] {label} [{self.count}/{self.total}] {time.monotonic() - self.t0:.1f}s{note}",
                  file=self.progress, flush=True)

    def expect_extra_call(self) -> None:
        """Announce one more call than planned (a corrective retry) so the [n/total] counter stays right."""
        with _PROGRESS_LOCK:
            self.total += 1

    def _attempt(self, system: str, messages: List[dict]) -> str:
        if self.limiter is None:
            return call_with_timeout(self.model, system, messages, self.timeout)
        with self.limiter:
            return call_with_timeout(self.model, system, messages, self.timeout)

    def call(self, stage: str, system: str, messages: List[dict], detail: str = "") -> str:
        last: Optional[ModelError] = None
        for attempt in (1, 2):
            try:
                out = self._attempt(system, messages)
            except ModelError as e:
                last = e
                continue
            self._say(stage, detail, " (after retry)" if attempt == 2 else "")
            return out
        kind = "timeout" if isinstance(last, CallTimeout) else "error"
        self._say(stage, detail, f" FAILED after 2 attempts ({kind})")
        raise CallFailed(f"{stage} call failed after 2 attempts: {last}") from None


def _list_with_count_retry(caller: "Caller", stage: str, system: str, user: str, detail: str, n: int,
                           what: str, shape: str):
    """Call, parse a JSON array and, if it has the wrong number of items, retry ONCE with the first reply
    and a short corrective instruction. Returns (items, error): `items` is the list (right count) or None,
    `error` the message to record when `items` is None. Unparseable replies are not retried; if the retry
    call itself fails, the first reply's count error stands."""
    messages = [{"role": "user", "content": user}]
    raw = caller.call(stage, system, messages, detail)
    try:
        items = extract_json_list(raw)
    except (ValueError, RecursionError) as e:
        return None, f"{stage} reply unusable: {e}"
    if len(items) == n:
        return items, ""
    first_err = f"{stage} reply unusable: expected {n} {what}, got {len(items)}"
    messages = messages + [
        {"role": "assistant", "content": raw},
        {"role": "user", "content": f"Your reply had {len(items)} entries but exactly {n} are expected "
                                    f"(one per item in the same order). Reply again with ONLY a JSON array "
                                    f"of exactly {n} {shape}."}]
    caller.expect_extra_call()
    try:
        raw2 = caller.call(stage, system, messages, f"{detail}, retry" if detail else "retry")
    except CallFailed:
        return None, first_err
    try:
        items = extract_json_list(raw2)
    except (ValueError, RecursionError) as e:
        return None, f"{stage} reply unusable: {e}"
    if len(items) != n:
        return None, f"{stage} reply unusable: expected {n} {what}, got {len(items)}"
    return items, ""


def _compaction_prompt(scenario: Scenario) -> str:
    return (
        "Save a checkpoint of the conversation below. The conversation follows, to the end of "
        "this message; every message is introduced by a line like `=== user ===`.\n\n"
        + render_transcript(scenario.messages)
    )


def _parse_compaction(raw: str):
    try:
        return extract_json(raw)
    except (ValueError, RecursionError) as e:
        raise ValidationError("compaction output", f"is not valid JSON ({e})") from None


def _compaction_handover(scenario: Scenario, model: Model, caller: Optional[Caller] = None):
    """OLD path: compaction call -> validate with the flat model -> render the flat brief (no store)."""
    raw = _call(caller, model, "compact", compaction_system_prompt(),
                [{"role": "user", "content": _compaction_prompt(scenario)}])
    cp = Checkpoint.from_dict(_parse_compaction(raw))  # ValidationError names the field
    return render_brief(cp), cp


def _problems(e: ValidationError) -> List[str]:
    return list(getattr(e, "problems", None) or [str(e)])


def _bundle_handover(scenario: Scenario, model: Model, caller: Optional[Caller] = None):
    """BUNDLE path: compaction call -> store.save() into a temp store (the same checks as the MCP tool)
    -> resume. If save is rejected, ONE retry with the error messages (decisions.md ruling 1).
    Returns (brief, checkpoint, save_info); raises ValidationError (with .save_info) when the save is
    still rejected after the retry."""
    system = compaction_system_prompt()
    messages = [{"role": "user", "content": _compaction_prompt(scenario)}]
    info: Dict[str, Any] = {"mode": "bundle", "rejected_first": False, "retry_needed": False,
                            "first_errors": [], "retry_errors": []}
    raw = _call(caller, model, "compact", system, messages)
    with tempfile.TemporaryDirectory(prefix="aic-eval-") as tmp:
        # fixed clock: the saved checkpoint (checkpoint.json) must not differ between runs
        store = GitStore(Path(tmp), clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
        attempt = 1
        while True:
            try:
                parsed = _parse_compaction(raw)
                res = store.save(parsed)
                break
            except ValidationError as e:
                errs = _problems(e)
                if attempt == 2:
                    info["retry_errors"] = errs
                    e.save_info = info  # type: ignore[attr-defined]
                    raise
                info["rejected_first"] = info["retry_needed"] = True
                info["first_errors"] = errs
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Your save was rejected. Nothing was saved.\n{e}\n"
                     "Reply again with ONE complete corrected JSON object (no prose)."}]
                if caller is not None:
                    caller.expect_extra_call()
                raw = _call(caller, model, "compact", system, messages, "retry")
                attempt = 2
        cp = store.get(res.checkpoint_id)  # what resume_checkpoint reads
        return render_brief(cp), cp, info, parsed  # parsed = the accepted attempt, before save-time redaction


def _call(caller: Optional[Caller], model: Model, stage: str, system: str, messages: List[dict], detail: str = "") -> str:
    if caller is None:
        return model.complete(system, messages)
    return caller.call(stage, system, messages, detail)


def _checkpoint_handover(scenario: Scenario, model: Model, caller: Optional[Caller],
                         handover_format: str = "bundle") -> Dict[str, Any]:
    if handover_format == "old":
        try:
            brief, cp = _compaction_handover(scenario, model, caller)
            return {"handover": brief, "error": None, "checkpoint": cp, "save_checks": {"mode": "old"}}
        except ValidationError as e:  # recorded, not fatal; model/API failures (ModelError) still abort
            return {"handover": None, "error": str(e), "save_checks": {"mode": "old"}}
    try:
        brief, cp, info, presave = _bundle_handover(scenario, model, caller)
        return {"handover": brief, "error": None, "checkpoint": cp, "save_checks": info, "presave": presave}
    except ValidationError as e:  # save checks still failing after the retry: recorded, not fatal
        info = getattr(e, "save_info", {"mode": "bundle", "rejected_first": False, "retry_needed": False,
                                        "first_errors": [], "retry_errors": []})
        return {"handover": None, "error": str(e), "save_checks": info}


def _summary_handover(scenario: Scenario, model: Model, caller: Optional[Caller]) -> Dict[str, Any]:
    summary = _call(
        caller, model, "summarize", SUMMARY_SYSTEM, [{"role": "user", "content": render_transcript(scenario.messages)}]
    ).strip()
    if summary:
        return {"handover": "Summary of the previous chat:\n\n" + summary, "error": None}
    return {"handover": None, "error": "summary model returned an empty reply"}


def _full_handover(scenario: Scenario) -> Dict[str, Any]:
    return {
        "handover": "Full transcript of the previous chat:\n\n" + render_transcript(scenario.messages),
        "error": None,
    }


def build_handovers(scenario: Scenario, model: Model, caller: Optional[Caller] = None,
                    handover_format: str = "bundle") -> Dict[str, Dict[str, Any]]:
    """variant -> {"handover": text | None, "error": str | None}."""
    out: Dict[str, Dict[str, Any]] = {}
    out["checkpoint"] = _checkpoint_handover(scenario, model, caller, handover_format)
    out["summary"] = _summary_handover(scenario, model, caller)
    out["full_history"] = _full_handover(scenario)
    return out


def _probe_entry(probe: Probe, answer: Optional[str], error: str) -> Dict[str, Any]:
    return {"question": probe.question, "answer": answer, "key_fact_recall": None, "contradictions": None,
            "facts": [{"fact": f, "present": None} for f in probe.key_facts], "error": error,
            "verbatim_exact_match": None, "stale_fact_use": None, "next_step_accuracy": None}


def answer_probes(caller: Caller, handover: str, probes: List[Probe], detail: str = "") -> List[Any]:
    """ONE fresh 'new chat' call: only the handover and all the questions.
    Returns one entry per probe: the answer text, or an error string wrapped as ("error", msg)."""
    n = len(probes)
    user = json.dumps({"questions": [p.question for p in probes]}, ensure_ascii=False)
    items, err = _list_with_count_retry(caller, "answer", ANSWER_SYSTEM + handover, user, detail, n,
                                        "answers", "strings")
    if items is None:
        return [("error", err)] * n
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
    items, err = _list_with_count_retry(caller, "judge", JUDGE_SYSTEM, payload, detail, n, "verdicts",
                                        "verdict objects")
    if items is None:
        return bad(err)
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
        "verbatim_exact_match": mean_or_none(p.get("verbatim_exact_match") for p in probes),
        "stale_fact_use": mean_or_none(p.get("stale_fact_use") for p in probes),
        "next_step_accuracy": mean_or_none(p.get("next_step_accuracy") for p in probes),
        "brief_tokens": brief_tokens,
        "probes_scored": len(scored),
        "probes_total": len(probes),
    }


def _eval_variant(caller: Caller, scenario: Scenario, name: str, h: Dict[str, Any],
                  strict_next_step: bool = False) -> Dict[str, Any]:
    """Answer + judge for one variant (judge starts right after this variant's own answer)."""
    if h["handover"] is None:
        return {
            "status": "failed", "error": h["error"], "handover_chars": None,
            "probes": [], "aggregate": _aggregate([], None),
        }
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
                probes.append({"question": pr.question, "answer": a, **verdicts[i],
                               **score_probe(pr.kind, pr.target, scenario.answer_key, a, strict_next_step)})
            else:
                probes.append(_probe_entry(pr, None, a[1]))
    except CallFailed as e:
        status, error = "failed", str(e)
        probes = [_probe_entry(pr, None, str(e)) for pr in scenario.probes]
    return {
        "status": status, "error": error, "handover_chars": len(text),
        "probes": probes, "aggregate": _aggregate(probes, estimate_tokens(text)),
    }


def run_scenario(scenario: Scenario, model: Model, timeout: Optional[float] = DEFAULT_TIMEOUT,
                 progress: Optional[TextIO] = None, workers: int = 1,
                 limiter: Optional[Any] = None, strict_next_step: bool = False,
                 handover_format: str = "bundle") -> Dict[str, Any]:
    """Run all variants and probes with 8 model calls: compaction, summary, then per variant one
    answer call and one judge call. Returns the JSON-ready results dict plus handover texts
    under the key ``_handovers`` (not part of the results file; the CLI writes them separately).
    Compaction/summary failures after the retry raise; answer/judge failures are recorded.
    With workers > 1 the independent calls run concurrently (never more than ``workers`` in flight,
    counted across every scenario sharing ``limiter``); results are identical to workers=1."""
    if workers > 1 and limiter is None:
        limiter = threading.BoundedSemaphore(workers)
    caller = Caller(model, scenario.name, timeout, progress, total=2 + 2 * len(VARIANTS),
                    limiter=limiter if workers > 1 else None)
    if workers <= 1:
        handovers = build_handovers(scenario, model, caller, handover_format)
        variants: Dict[str, Any] = {name: _eval_variant(caller, scenario, name, handovers[name], strict_next_step) for name in VARIANTS}
    else:
        # compaction || summary || full_history answer; each variant's judge follows its own answer
        makers = {
            "checkpoint": lambda: _checkpoint_handover(scenario, model, caller, handover_format),
            "summary": lambda: _summary_handover(scenario, model, caller),
            "full_history": lambda: _full_handover(scenario),
        }

        def chain(name: str):
            h = makers[name]()
            return h, _eval_variant(caller, scenario, name, h, strict_next_step)

        with ThreadPoolExecutor(max_workers=len(VARIANTS)) as ex:
            futs = {name: ex.submit(chain, name) for name in VARIANTS}
            outcomes: Dict[str, Any] = {}
            first_exc: Optional[BaseException] = None
            for name in VARIANTS:  # fixed order; waits for every task before leaving the with-block
                try:
                    outcomes[name] = futs[name].result()
                except BaseException as e:  # noqa: BLE001 - re-raised below
                    first_exc = first_exc or e
        if first_exc is not None:
            raise first_exc
        handovers = {name: outcomes[name][0] for name in VARIANTS}
        variants = {name: outcomes[name][1] for name in VARIANTS}
    result = {
        "scenario": scenario.name,
        "description": scenario.description,
        "model": model.name,
        "messages": len(scenario.messages),
        "probe_count": len(scenario.probes),
        "variants": variants,
        "_handovers": {k: v["handover"] for k, v in handovers.items()},
    }
    result["variants"]["checkpoint"]["save_checks"] = handovers["checkpoint"].get("save_checks")
    cp = handovers["checkpoint"].get("checkpoint")
    if cp is not None:
        result["_checkpoint"] = cp.to_dict()  # saved as checkpoint.json so `rescore` can score the workspace exactly
    if scenario.environment:
        result["workspace_capture"] = _workspace_capture(scenario, handovers["checkpoint"])
    return result


def _workspace_capture(scenario: Scenario, ck: Dict[str, Any]) -> Dict[str, Any]:
    """Stage-1 capture scoring from the compacted checkpoint (code only, no model call)."""
    cp = ck.get("checkpoint")
    if cp is None:
        return {"status": "failed", "error": ck.get("error"), "capture_recall": None, "capture_precision": None,
                "status_accuracy": None, "secret_leakage": None}
    presave = ck.get("presave")
    if presave is not None:
        # bundle path: measure the model's own parsed output (the attempt that was saved), BEFORE
        # store.save() redacted it, so secret_leakage means the same as on the old path
        ws, blob = presave.get("workspace") if isinstance(presave, dict) else None, json.dumps(presave, ensure_ascii=False)
    else:
        ws, blob = cp.workspace, json.dumps(cp.to_dict(), ensure_ascii=False)
    scores = capture_scores(scenario.environment or {}, cp.workspace, scenario.secret_values, [blob, ck["handover"] or ""])
    if presave is not None:
        scores = {**scores, "secret_leakage": capture_scores(
            scenario.environment or {}, ws, scenario.secret_values, [blob])["secret_leakage"]}
    return {"status": "ok", "error": None, **scores}
