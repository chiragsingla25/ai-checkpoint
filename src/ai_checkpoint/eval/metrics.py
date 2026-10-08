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


_HISTORY_CUE = re.compile(
    r"\b(original(?:ly)?|earlier|previous(?:ly)?|prior|former(?:ly)?|old(?:er)?|initial(?:ly)?|"
    r"draft|supersed\w*|replac\w*|chang(?:ed|es)|correct(?:ed|ion)|updat\w*|outdated|obsolete|stale|"
    r"wrong|incorrect|mistaken|no longer|used to|but now|considered|proposed|suggested|thought|assumed)\b", re.I)
_NEGATED = re.compile(r"(?:\bnot|\bnever|n't|\bno|\binstead of|\brather than)\W+(?:\w+\W+){0,2}$", re.I)
# clause boundaries: sentence end, newline, colon, comma, semicolon (unless it continues with was/is...),
# parentheses, and the conjunctions but/so/yet/however/although/though/whereas
_CLAUSE_SPLIT = re.compile(
    r"(?<=[.!?])\s+|\n+|:\s+|,\s+|;\s+(?!(?:was|were|is|are|had|has)\b)|\s+\(|\)\s*|"
    r"\s+(?:but|so|yet|however|although|though|whereas)\s+", re.I)


def _spans(text: str, value: str) -> List[Tuple[int, int]]:
    v = value.strip()
    if not v:
        return []
    pat = r"(?<![A-Za-z0-9])(?<!\d[.,])" + re.escape(v) + r"(?![A-Za-z0-9])(?![.,]\d)"
    return [m.span() for m in re.finditer(pat, text, flags=re.I)]


def _clauses(text: str) -> List[Tuple[int, int]]:
    out, pos = [], 0
    for m in _CLAUSE_SPLIT.finditer(text):
        out.append((pos, m.start()))
        pos = m.end()
    out.append((pos, len(text)))
    return [(x, y) for x, y in out if y > x]


def _asserted(text: str, spans: List[Tuple[int, int]], clauses: List[Tuple[int, int]]) -> List[int]:
    """Start positions of the occurrences that the answer ASSERTS: not negated ("not 48 hours") and in a
    clause with no history cue (original / earlier / replaced / superseded / was wrong ...)."""
    hist = [bool(_HISTORY_CUE.search(text[a:b])) for a, b in clauses]
    for i in range(len(clauses) - 1):  # "...48 hours but that is outdated": the next clause judges this one
        if hist[i + 1] and re.match(r"(?:that|it|this|which|they|these)\b", text[clauses[i + 1][0]:], re.I):
            hist[i] = True
    out = []
    for st, en in spans:
        idx = next((i for i, c in enumerate(clauses) if c[0] <= st < c[1]), None)
        cs = clauses[idx][0] if idx is not None else 0
        if (hist[idx] if idx is not None else False) or _NEGATED.search(text[cs:st]):
            continue
        out.append(st)
    return out


def stale_fact_use(answer: str, old: str, new: str = "") -> int:
    """1 if the answer asserts the corrected-away value `old` as the current one (stale), else 0.

    HEURISTIC, string based, no language model. The answer is cut into clauses; an occurrence of a value
    is "asserted" unless its clause contains a history cue (original, earlier, previously, replaced,
    superseded, corrected, draft, wrong, outdated, considered ...) or it is negated ("not 48 hours",
    "instead of ..."). Then:
      - `old` absent (or only inside `new` / a longer token)      -> 0
      - `old` present, `new` absent                               -> 1
      - both present: 1 when no `new` is asserted and `old` is, or when the LAST asserted value
        (the conclusion) is `old`; 0 when `old` is only history / negated, or `new` is asserted last.
    Known limits: a cue anywhere in a clause marks every value in it as history ("the old SQL says 24
    hours" is 0 even if it is the answer's conclusion); a cue-free sentence about a different quantity
    that happens to contain `old` counts as asserting it; values attributed to a source ("the handover
    says 48 hours") count as asserted; an answer with both values asserted is judged by order only;
    only English cue words are known; an answer with `old` but no `new` is 1 even if `old` is called
    history. Use the judge's contradiction count alongside this metric."""
    masked = answer
    if new.strip() and old.strip() in new:
        masked = re.sub(re.escape(new.strip()), lambda m: " " * len(m.group(0)), masked, flags=re.I)
    old_spans = _spans(masked, old)
    if not old_spans:
        return 0
    new_spans = _spans(answer, new) if new.strip() else []
    if not new_spans:
        return 1
    clauses = _clauses(answer)
    old_at = _asserted(answer, old_spans, clauses)
    new_at = _asserted(answer, new_spans, clauses)
    if not old_at:
        return 0
    if not new_at:
        return 1
    return int(max(old_at) > max(new_at))


def _term_alternatives(term: str) -> List[str]:
    """Lower-case spellings that satisfy a required term in lenient mode. A filename such as
    `0023_add_event_dedupe.sql` is also satisfied by its stem, its descriptive part, or its
    leading number as a whole number (`0023` but not `00230` or `10023`)."""
    t = term.strip().lower()
    alts = [t]
    m = re.fullmatch(r"(?P<stem>[^/\\]*?)\.[a-z0-9]{1,5}", t.rsplit("/", 1)[-1])
    if m:
        stem = m.group("stem")
        alts.append(stem)
        m2 = re.fullmatch(r"(\d+)[_\-. ]+(.+)", stem)
        if m2:
            alts += [m2.group(1), m2.group(2)]
    return alts


def _has_term(low: str, alt: str) -> bool:
    if alt.isdigit():
        return re.search(r"(?<!\d)" + re.escape(alt) + r"(?!\d)", low) is not None
    return alt in low


def next_step_correct(answer: str, required_terms: List[str], strict: bool = False) -> int:
    """1 if the answer contains every required term (case-insensitive), else 0. Lenient by default:
    a filename term also matches its stem, descriptive part or leading number (see
    `_term_alternatives`). `strict=True` requires each term literally."""
    low = answer.lower()
    if not required_terms:
        return 0
    if strict:
        return int(all(t.lower() in low for t in required_terms))
    return int(all(any(_has_term(low, a) for a in _term_alternatives(t)) for t in required_terms))


def score_probe(kind: str, target: str, answer_key: Optional[dict], answer: Optional[str],
                strict_next_step: bool = False) -> Dict[str, Optional[int]]:
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
            out["next_step_accuracy"] = next_step_correct(answer, answer_key["next_step"]["required_terms"], strict_next_step)
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


PATH_CATEGORIES = ("files", "repos", "access")  # the same location may be filed under any of these

_STATUSES = ("still_relevant", "done_with")


def _paths_match(a: str, b: str) -> bool:
    """Equal, or one is a suffix of the other on a path-segment boundary (`data/raw` vs `~/work/x/data/raw`)."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return bool(short) and short not in ("~", "/") and long_.endswith("/" + short)


def _keys_match(cat: str, ks1: List[str], ks2: List[str]) -> bool:
    if cat in PATH_CATEGORIES:
        return any(_paths_match(x, y) for x in ks1 for y in ks2)
    return bool(set(ks1) & set(ks2))


def capture_scores(manifest: dict, workspace: Optional[dict], secret_values: List[str],
                   texts: Iterable[str] = ()) -> Dict[str, Any]:
    """Score a checkpoint's workspace section against the manifest.

    capture_recall        matched manifest items / manifest items
    recall_still_relevant the same, over manifest items with status still_relevant (None if there are none)
    recall_done_with      the same, over manifest items with status done_with (None if there are none)
    capture_precision     workspace items matching a manifest item / workspace items (None if the workspace is empty)
    status_accuracy       matched items with the right status / matched items (None if nothing matched)
    secret_leakage        number of DISTINCT secret values found in `texts` or the workspace itself
    Matching: category tools/connectors/env_vars/skills/references need the same category and the same
    normalised key (trailing slash, `$HOME` vs `~`). Paths match when equal or when one is a suffix of the
    other on a path-segment boundary. For recall, a path may be filed under files, repos or access
    interchangeably; precision and status accuracy compare within the manifest item's own category."""
    workspace = workspace or {}
    m_items: List[Tuple[str, List[str], str]] = []
    for cat in WORKSPACE_CATEGORIES:
        for it in manifest.get(cat, []) or []:
            m_items.append((cat, _keys(cat, it), it.get("status", "")))
    w_items: List[Tuple[str, List[str], str]] = []
    for cat in WORKSPACE_CATEGORIES:
        for it in workspace.get(cat, []) or []:
            w_items.append((cat, _keys(cat, it), it.get("status", "")))

    def find(cat: str, keys: List[str], pool: List[Tuple[str, List[str], str]], cross: bool = False):
        """Status of the first pool item matching; `cross` also looks across files/repos/access."""
        for c, ks, st in pool:
            if (c == cat or (cross and cat in PATH_CATEGORIES and c in PATH_CATEGORIES)) and _keys_match(cat, ks, keys):
                return st
        return None

    recalled = [find(c, ks, w_items, cross=True) is not None for c, ks, _ in m_items]
    same_cat = [(st, find(c, ks, w_items)) for c, ks, st in m_items]
    same_cat = [(st, wst) for st, wst in same_cat if wst is not None]
    matched_w = sum(1 for c, ks, _ in w_items if find(c, ks, m_items) is not None)
    right = sum(1 for st, wst in same_cat if st == wst)
    blob = "\n".join(list(texts) + [json.dumps(workspace, ensure_ascii=False)])
    leak = len({s for s in secret_values if s and s in blob})

    def recall_for(status: str) -> Optional[float]:
        flags = [r for r, (_, _, st) in zip(recalled, m_items) if st == status]
        return _round(sum(flags) / len(flags)) if flags else None

    return {
        "capture_recall": _round(sum(recalled) / len(m_items)) if m_items else None,
        "recall_still_relevant": recall_for("still_relevant"),
        "recall_done_with": recall_for("done_with"),
        "capture_precision": _round(matched_w / len(w_items)) if w_items else None,
        "status_accuracy": _round(right / len(same_cat)) if same_cat else None,
        "secret_leakage": leak,
        "manifest_items": len(m_items),
        "workspace_items": len(w_items),
        "matched": sum(recalled),
    }


# ------------------------------------------------------------------ workspace from a saved brief

_SETUP_TITLES = (
    ("Folders to ask the user for access to", "access"),
    ("Connectors to check", "connectors"),
    ("Repos", "repos"),
    ("Tools and setup", "tools"),
    ("Environment variables that must be set (names only)", "env_vars"),
    ("Skills, plugins and agents", "skills"),
    ("Files to open", "files"),
    ("References", "references"),
)


def _split_items(text: str) -> List[str]:
    """Split on '; ' that is outside parentheses."""
    out, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        depth += ch == "("
        depth -= ch == ")" and depth > 0
        if depth == 0 and text.startswith("; ", i):
            out.append(cur)
            cur, i = "", i + 2
            continue
        cur += ch
        i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def workspace_from_brief(brief: str) -> Optional[dict]:
    """Rebuild an approximate workspace from the 'Set up first' section of a rendered brief (every item
    there is still_relevant; done_with items are never rendered). None when the brief has no such section."""
    m = re.search(r"^## Set up first\s*\n(.*?)(?=^## |\Z)", brief, flags=re.M | re.S)
    if not m:
        return None
    ws: Dict[str, list] = {cat: [] for cat in WORKSPACE_CATEGORIES}
    for line in m.group(1).splitlines():
        if not line.startswith("- "):
            continue
        for title, cat in _SETUP_TITLES:
            if line.startswith(f"- {title}: "):
                key_field = WORKSPACE_CATEGORIES[cat][0]
                for item in _split_items(line[len(f"- {title}: "):]):
                    cut = [i for i in (item.find(" ("), item.find(" - ")) if i > 0]
                    key = (item[:min(cut)] if cut else item).strip().rstrip(".")
                    if key:
                        ws[cat].append({key_field: key, "status": "still_relevant"})
                break
    return ws
