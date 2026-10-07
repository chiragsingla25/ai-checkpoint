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
      "known_wrong": ["optional plausible wrong claims, e.g. a rejected option stated as chosen"]
    }
  ]
}
```
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from ..errors import CheckpointError


class ScenarioError(CheckpointError):
    """The scenario file is missing, unreadable or malformed."""


@dataclass
class Probe:
    question: str
    key_facts: List[str]
    reference: str = ""
    must_not_contradict: List[str] = field(default_factory=list)
    known_wrong: List[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    messages: List[dict]
    probes: List[Probe]
    description: str = ""


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
            )
        )
    name = data.get("name", default_name)
    desc = data.get("description", "")
    if not isinstance(name, str) or not name.strip():
        _fail("name", "must be a non-empty string")
    if not isinstance(desc, str):
        _fail("description", "must be a string")
    return Scenario(name=name.strip(), messages=messages, probes=probes, description=desc)


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
