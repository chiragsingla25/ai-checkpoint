"""Scenario file format (JSON) and its validation.

```
{
  "name": "optional-short-name",            # default: file name without extension
  "description": "optional text",
  "messages": [                             # the conversation to hand over, non-empty
    {"role": "user" | "assistant", "content": "text"}, ...
  ],
  "probes": [                               # non-empty
    {
      "question": "asked in a fresh chat that only has the handover",
      "key_facts": ["fact that a correct answer contains", ...],   # non-empty
      "reference": "optional reference answer (default: key facts joined)",
      "must_not_contradict": ["optional true statements the answer must not contradict"],
      "known_wrong": ["optional plausible wrong claims, e.g. a rejected option stated as chosen"],
      "kind": "optional: fact | decision | verbatim | stale | next_step",
      "target": "optional pointer into answer_key, e.g. verbatim[0], decisions[1], correction, next_step"
    }
  ],
  "answer_key": {                           # optional, written by the dataset generator
    "decisions": [{"topic", "decision", "reason", "rejected"}],
    "verbatim": [{"label", "type": "number|command|code", "text"}],
    "correction": {"what", "old", "new"},
    "next_step": {"text", "required_terms": [...]}
  },
  "environment": {                          # optional manifest, keyed by checkpoint workspace category
    "files": [{"path", "status": "still_relevant|done_with", "trap": "optional label", "note": "optional"}],
    "repos": [{"path", "branch", "last_commit", "status"}], "env_vars": [{"name", "status"}], ...
  },
  "secret_values": ["fake secret strings that appear in the chat and must never be captured"]
}
```
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from ..errors import CheckpointError
from ..model import STATUS_VALUES, WORKSPACE_CATEGORIES

PROBE_KINDS = ("fact", "decision", "verbatim", "stale", "next_step")


class ScenarioError(CheckpointError):
    """The scenario file is missing, unreadable or malformed."""


@dataclass
class Probe:
    question: str
    key_facts: List[str]
    reference: str = ""
    must_not_contradict: List[str] = field(default_factory=list)
    known_wrong: List[str] = field(default_factory=list)
    kind: str = ""
    target: str = ""


@dataclass
class Scenario:
    name: str
    messages: List[dict]
    probes: List[Probe]
    description: str = ""
    answer_key: Optional[dict] = None
    environment: Optional[dict] = None
    secret_values: List[str] = field(default_factory=list)


def _fail(where: str, msg: str):
    raise ScenarioError(f"{where}: {msg}")


def _tname(v: Any) -> str:
    return "null" if v is None else type(v).__name__


def _nonempty_str(v: Any, where: str) -> str:
    if v is None:
        _fail(where, "is required")
    if not isinstance(v, str):
        _fail(where, f"must be a string, got {_tname(v)}")
    if not v.strip():
        _fail(where, "must not be empty")
    return v


def _str_list(v: Any, where: str, *, required: bool) -> List[str]:
    if v is None:
        if required:
            _fail(where, "is required (a non-empty list of strings)")
        return []
    if not isinstance(v, list):
        _fail(where, f"must be a list of strings, got {_tname(v)}")
    if required and not v:
        _fail(where, "must not be empty")
    return [_nonempty_str(x, f"{where}[{i}]") for i, x in enumerate(v)]


def _opt_str(v: Any, where: str) -> str:
    if v is None:
        return ""
    return _nonempty_str(v, where)


def _kind(v: Any, where: str) -> str:
    if v is None:
        return ""
    if v not in PROBE_KINDS:
        _fail(where, f"must be one of {', '.join(PROBE_KINDS)}, got {v!r}")
    return v


def _obj(v: Any, where: str) -> dict:
    if not isinstance(v, dict):
        _fail(where, f"must be an object, got {_tname(v)}")
    return v


def _obj_list(v: Any, where: str) -> list:
    if not isinstance(v, list):
        _fail(where, f"must be a list, got {_tname(v)}")
    return [_obj(x, f"{where}[{i}]") for i, x in enumerate(v)]


def _answer_key(v: Any) -> Optional[dict]:
    if v is None:
        return None
    w = "answer_key"
    _obj(v, w)
    for i, d in enumerate(_obj_list(v.get("decisions", []), f"{w}.decisions")):
        for k in ("decision", "reason", "rejected"):
            _nonempty_str(d.get(k), f"{w}.decisions[{i}].{k}")
    for i, d in enumerate(_obj_list(v.get("verbatim", []), f"{w}.verbatim")):
        _nonempty_str(d.get("text"), f"{w}.verbatim[{i}].text")
    corr = v.get("correction")
    if corr is not None:
        _obj(corr, f"{w}.correction")
        for k in ("old", "new"):
            _nonempty_str(corr.get(k), f"{w}.correction.{k}")
    ns = v.get("next_step")
    if ns is not None:
        _obj(ns, f"{w}.next_step")
        _nonempty_str(ns.get("text"), f"{w}.next_step.text")
        _str_list(ns.get("required_terms"), f"{w}.next_step.required_terms", required=True)
    return v


def _environment(v: Any) -> Optional[dict]:
    if v is None:
        return None
    w = "environment"
    _obj(v, w)
    for cat, items in v.items():
        if cat not in WORKSPACE_CATEGORIES:
            _fail(f"{w}.{cat}", "unknown category (expected one of " + ", ".join(WORKSPACE_CATEGORIES) + ")")
        key = WORKSPACE_CATEGORIES[cat][0]
        for i, it in enumerate(_obj_list(items, f"{w}.{cat}")):
            _nonempty_str(it.get(key), f"{w}.{cat}[{i}].{key}")
            st = it.get("status")
            if st not in STATUS_VALUES:
                _fail(f"{w}.{cat}[{i}].status", f"must be one of {', '.join(STATUS_VALUES)}, got {st!r}")
            _opt_str(it.get("trap"), f"{w}.{cat}[{i}].trap")
    return v


def parse_scenario(data: Any, default_name: str = "scenario") -> Scenario:
    if not isinstance(data, dict):
        _fail("scenario", f"must be a JSON object, got {_tname(data)}")
    msgs = data.get("messages")
    if msgs is None:
        _fail("messages", "is required (the conversation as a list of {role, content})")
    if not isinstance(msgs, list):
        _fail("messages", f"must be a list, got {_tname(msgs)}")
    if not msgs:
        _fail("messages", "must not be empty")
    messages = []
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            _fail(f"messages[{i}]", f"must be an object with role and content, got {_tname(m)}")
        role = m.get("role")
        if role not in ("user", "assistant"):
            _fail(f"messages[{i}].role", f"must be 'user' or 'assistant', got {role!r}")
        messages.append({"role": role, "content": _nonempty_str(m.get("content"), f"messages[{i}].content")})
    probes_raw = data.get("probes")
    if probes_raw is None:
        _fail("probes", "is required (a non-empty list of probes)")
    if not isinstance(probes_raw, list):
        _fail("probes", f"must be a list, got {_tname(probes_raw)}")
    if not probes_raw:
        _fail("probes", "must not be empty")
    probes = []
    for i, p in enumerate(probes_raw):
        w = f"probes[{i}]"
        if not isinstance(p, dict):
            _fail(w, f"must be an object, got {_tname(p)}")
        facts = _str_list(p.get("key_facts"), f"{w}.key_facts", required=True)
        ref = p.get("reference")
        reference = _nonempty_str(ref, f"{w}.reference") if ref is not None else "; ".join(facts)
        probes.append(
            Probe(
                question=_nonempty_str(p.get("question"), f"{w}.question"),
                key_facts=facts,
                reference=reference,
                must_not_contradict=_str_list(p.get("must_not_contradict"), f"{w}.must_not_contradict", required=False),
                known_wrong=_str_list(p.get("known_wrong"), f"{w}.known_wrong", required=False),
                kind=_kind(p.get("kind"), f"{w}.kind"),
                target=_opt_str(p.get("target"), f"{w}.target"),
            )
        )
    name = data.get("name", default_name)
    desc = data.get("description", "")
    if not isinstance(name, str) or not name.strip():
        _fail("name", "must be a non-empty string")
    if not isinstance(desc, str):
        _fail("description", "must be a string")
    return Scenario(
        name=name.strip(),
        messages=messages,
        probes=probes,
        description=desc,
        answer_key=_answer_key(data.get("answer_key")),
        environment=_environment(data.get("environment")),
        secret_values=_str_list(data.get("secret_values"), "secret_values", required=False),
    )


def load_scenario(path) -> Scenario:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ScenarioError(f"scenario file not found: {p}") from None
    except (OSError, UnicodeDecodeError) as e:
        raise ScenarioError(f"cannot read scenario file {p}: {e}") from None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as e:
        raise ScenarioError(f"{p} is not valid JSON: {e}") from None
    return parse_scenario(data, default_name=p.stem)
