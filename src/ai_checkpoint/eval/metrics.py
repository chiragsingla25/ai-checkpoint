"""Metrics computed by code (no model calls): verbatim exact match, stale-fact use, next-step
accuracy, and workspace capture scoring against an environment manifest."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..model import WORKSPACE_CATEGORIES

# ------------------------------------------------------------------ answer scores


def verbatim_exact_match(answer: str, text: str) -> int:
    """1 if the answer contains the verbatim text byte-for-byte (only surrounding whitespace of
    either side is ignored), else 0. No case folding, no reordering, no rounding. Where the
    text starts or ends with a letter or digit it must not continue into a longer token
    (`868` is not in `8680` or `1868`, `0.873` is not in `0.8732`); `868,` and `868.` still match."""
    needle = text.strip()
    if not needle:
        return 0
    pat = re.escape(needle)
    if needle[0].isalnum():
        pat = r"(?<![A-Za-z0-9])(?<!\d[.,])" + pat
    if needle[-1].isalnum():
        pat += r"(?![A-Za-z0-9])(?![.,]\d)"
    return int(re.search(pat, answer.strip()) is not None)


def _contains_value(answer: str, value: str) -> bool:
    """Substring match that does not fire inside a longer token (`50` is not in `500`, `1.5`)."""
    v = value.strip()
    if not v:
        return False
    pat = r"(?<![A-Za-z0-9])(?<!\d[.,])" + re.escape(v) + r"(?![A-Za-z0-9])(?![.,]\d)"
    return re.search(pat, answer, flags=re.I) is not None


def stale_fact_use(answer: str, old: str, new: str = "") -> int:
    """1 if the answer states the corrected-away value `old` (stale), else 0. An answer that
    contains `old` only as part of `new` (or a longer token) does not count."""
    cleaned = answer
    if new.strip() and old.strip() in new:
        cleaned = re.sub(re.escape(new.strip()), " ", cleaned, flags=re.I)
    return int(_contains_value(cleaned, old))


def next_step_correct(answer: str, required_terms: List[str]) -> int:
    """1 if the answer contains every required term (case-insensitive), else 0."""
    low = answer.lower()
    return int(bool(required_terms) and all(t.lower() in low for t in required_terms))


def score_probe(kind: str, target: str, answer_key: Optional[dict], answer: Optional[str]) -> Dict[str, Optional[int]]:
    """Per-probe code scores; each is None when it does not apply (or the answer is missing)."""
    out: Dict[str, Optional[int]] = {"verbatim_exact_match": None, "stale_fact_use": None, "next_step_accuracy": None}
    if not answer_key or answer is None or not kind:
        return out
    try:
        if kind == "verbatim":
            m = re.fullmatch(r"verbatim\[(\d+)\]", target)
            out["verbatim_exact_match"] = verbatim_exact_match(answer, answer_key["verbatim"][int(m.group(1))]["text"])
        elif kind == "stale":
            c = answer_key["correction"]
            out["stale_fact_use"] = stale_fact_use(answer, c["old"], c.get("new", ""))
        elif kind == "next_step":
            out["next_step_accuracy"] = next_step_correct(answer, answer_key["next_step"]["required_terms"])
    except (KeyError, IndexError, TypeError, AttributeError):
        pass  # unresolvable target: not scored
    return out


def mean_or_none(values: Iterable[Optional[int]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


# ------------------------------------------------------------------ workspace capture


def norm_key(cat: str, key: str) -> str:
    k = key.strip().strip("`'\"").strip()
    k = re.sub(r"^\$\{?HOME\}?(?=/|$)", "~", k)
    if cat in ("files", "repos", "access"):
        if k.startswith("./"):
            k = k[2:]
        k = k.rstrip("/") or "/"
    return k.lower()


def _keys(cat: str, item: dict) -> List[str]:
    key_field = WORKSPACE_CATEGORIES[cat][0]
    keys = [norm_key(cat, str(item.get(key_field, "")))]
    if cat == "references" and item.get("url"):
        keys.append(norm_key(cat, str(item["url"])))
    return keys


def _round(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 4)


def capture_scores(manifest: dict, workspace: Optional[dict], secret_values: List[str],
                   texts: Iterable[str] = ()) -> Dict[str, Any]:
    """Score a checkpoint's workspace section against the manifest.

    capture_recall    matched manifest items / manifest items
    capture_precision matched workspace items / workspace items (None if the workspace is empty)
    status_accuracy   matched items with the right status / matched items (None if nothing matched)
    secret_leakage    number of DISTINCT secret values found in `texts` or the workspace itself
    Matching: same category and same normalised key (trailing slash, `$HOME` vs `~`)."""
    workspace = workspace or {}
    m_items: List[Tuple[str, List[str], str]] = []
    for cat in WORKSPACE_CATEGORIES:
        for it in manifest.get(cat, []) or []:
            m_items.append((cat, _keys(cat, it), it.get("status", "")))
    w_items: List[Tuple[str, List[str], str]] = []
    for cat in WORKSPACE_CATEGORIES:
        for it in workspace.get(cat, []) or []:
            w_items.append((cat, _keys(cat, it), it.get("status", "")))

    def find(cat: str, keys: List[str], pool: List[Tuple[str, List[str], str]]):
        for c, ks, st in pool:
            if c == cat and set(ks) & set(keys):
                return st
        return None

    matched_m = [(c, st, find(c, ks, w_items)) for c, ks, st in m_items]
    matched_m = [(c, st, wst) for c, st, wst in matched_m if wst is not None]
    matched_w = sum(1 for c, ks, _ in w_items if find(c, ks, m_items) is not None)
    right = sum(1 for _, st, wst in matched_m if st == wst)
    blob = "\n".join(list(texts) + [json.dumps(workspace, ensure_ascii=False)])
    leak = len({s for s in secret_values if s and s in blob})
    return {
        "capture_recall": _round(len(matched_m) / len(m_items)) if m_items else None,
        "capture_precision": _round(matched_w / len(w_items)) if w_items else None,
        "status_accuracy": _round(right / len(matched_m)) if matched_m else None,
        "secret_leakage": leak,
        "manifest_items": len(m_items),
        "workspace_items": len(w_items),
        "matched": len(matched_m),
    }
