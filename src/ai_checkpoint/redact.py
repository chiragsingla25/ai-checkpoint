"""Best-effort secret redaction. Stdlib only.

Applied to every text field before a checkpoint is written, so secrets never
reach disk or git history. Ordinary text and code are left byte-for-byte
unchanged; only the matched secret is replaced by ``[REDACTED]``.
"""
from __future__ import annotations

import re
from typing import Any

MARKER = "[REDACTED]"

_B = r"(?<![A-Za-z0-9])"

#: Whole-token patterns: the entire match is replaced.
_TOKEN_PATTERNS = [
    re.compile(p)
    for p in (
        _B + r"sk-ant-[A-Za-z0-9_\-]{6,}",
        _B + r"sk-[A-Za-z0-9_\-]{16,}",
        _B + r"gh[pousr]_[A-Za-z0-9]{16,}",
        _B + r"github_pat_[A-Za-z0-9_]{16,}",
        _B + r"(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9])",
        _B + r"AIza[0-9A-Za-z_\-]{35}",
        _B + r"xox[abprs]-[A-Za-z0-9\-]{10,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
    )
]
_TOKEN_PATTERNS[-1] = re.compile(_TOKEN_PATTERNS[-1].pattern, re.DOTALL)

_BEARER = re.compile(r"\b(Bearer)([ \t]+)([A-Za-z0-9._~+/=\-]{7,}[A-Za-z0-9_~+/=\-])", re.IGNORECASE)

_KEYWORD = r"(?:secret|token|password|passwd|api[_\-]?key)(?:[_\-](?:key|token|value))?(?![A-Za-z])"
_PREFIX = r"[A-Za-z0-9_.\-]*"
# key=value (unquoted or quoted value)
_ASSIGN = re.compile(
    r"(?P<pre>" + _PREFIX + _KEYWORD + r"[ \t]*=[ \t]*)"
    r"(?P<val>\"[^\"\n]+\"|'[^'\n]+'|[^\s'\"`,;&()\[\]{}]{4,})",
    re.IGNORECASE,
)
# "key": "value" (JSON / dict literals)
_JSON_ASSIGN = re.compile(
    r"(?P<pre>[\"']" + _PREFIX + _KEYWORD + r"[\"'][ \t]*:[ \t]*)(?P<val>\"[^\"\n]+\"|'[^'\n]+')",
    re.IGNORECASE,
)

# scheme://user:SECRET@host -- only the password/token part is replaced
_URL_CRED = re.compile(
    r"(?P<pre>\b[A-Za-z][A-Za-z0-9+.\-]*://[^\s/:@'\"`<>]+:)(?P<pw>[^\s/@'\"`<>]+)(?=@)"
)

_PLACEHOLDER_START = ("$", "<", "{", "%", "[REDACTED")
_NON_SECRET_WORDS = {"none", "null", "true", "false", "nil", "undefined"}


def _bearer_sub(m: re.Match) -> str:
    tok = m.group(3)
    if tok.isalpha() and tok.islower():  # "Bearer authentication" is prose
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}{MARKER}"


def _assign_sub(m: re.Match) -> str:
    val = m.group("val")
    if val[0] in "\"'":
        inner = val[1:-1]
        if inner.startswith(_PLACEHOLDER_START) or inner.lower() in _NON_SECRET_WORDS:
            return m.group(0)
        return m.group("pre") + val[0] + MARKER + val[-1]
    if val.startswith(_PLACEHOLDER_START) or val.lower() in _NON_SECRET_WORDS:
        return m.group(0)
    nxt = m.string[m.end() : m.end() + 1]
    if nxt in ("(", "["):  # function call / lookup, e.g. token=get_token()
        return m.group(0)
    return m.group("pre") + MARKER


def _url_cred_sub(m: re.Match) -> str:
    pw = m.group("pw")
    if pw.startswith(_PLACEHOLDER_START):
        return m.group(0)
    return m.group("pre") + MARKER


def redact_text(text: str) -> str:
    """Replace secrets in ``text`` with ``[REDACTED]``. Idempotent."""
    for pat in _TOKEN_PATTERNS:
        text = pat.sub(MARKER, text)
    text = _URL_CRED.sub(_url_cred_sub, text)
    text = _BEARER.sub(_bearer_sub, text)
    text = _JSON_ASSIGN.sub(_assign_sub, text)
    text = _ASSIGN.sub(_assign_sub, text)
    return text


def redact_obj(obj: Any) -> Any:
    """Recursively redact every string in dicts/lists/tuples; other values pass through."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj
