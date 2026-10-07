"""Model interface, the deterministic FakeModel, and lazy Anthropic/OpenAI adapters."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Protocol

from ..errors import CheckpointError

Message = Dict[str, str]  # {"role": "user"|"assistant", "content": str}

TASK_COMPACT = "TASK: COMPACT"
TASK_SUMMARIZE = "TASK: SUMMARIZE"
TASK_ANSWER = "TASK: ANSWER"
TASK_JUDGE = "TASK: JUDGE"

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-5",
}
MODEL_ENV = {
    "anthropic": "CHECKPOINT_EVAL_ANTHROPIC_MODEL",
    "openai": "CHECKPOINT_EVAL_OPENAI_MODEL",
}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
MODEL_CHOICES = ("fake", "anthropic", "openai")


class ModelError(CheckpointError):
    """A model could not be used or a call to it failed."""


class Model(Protocol):
    name: str

    def complete(self, system: str, messages: List[Message]) -> str: ...


# ------------------------------------------------------------------ fake
_STOP = set(
    "a an the of to in on for and or is are was were be been it its this that these those "
    "what which who how why when where do does did we you i our your with as at by from "
    "so not no if then than can could should would will".split()
)
_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w.\-/:%$]+", " ", text.lower())).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in norm(text).split() if t not in _STOP]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s and s.strip()]


def _first(text: str, limit: int = 300) -> str:
    s = _sentences(text.replace("```", " "))
    return (s[0] if s else text.strip())[:limit] or "(empty)"


_TRANSCRIPT_RE = re.compile(r"^=== (user|assistant) ===\n", re.M)


def parse_transcript(text: str) -> List[Message]:
    """Inverse of pipeline.render_transcript."""
    parts = _TRANSCRIPT_RE.split(text)
    return [
        {"role": parts[i], "content": parts[i + 1].strip("\n")}
        for i in range(1, len(parts) - 1, 2)
    ]


class FakeModel:
    """Deterministic stand-in: heuristics over the text it is given, no randomness.

    Its outputs are plausible enough to exercise the whole pipeline; the scores
    it produces say nothing about real models.
    """

    name = "fake"

    def complete(self, system: str, messages: List[Message]) -> str:
        user = messages[-1]["content"] if messages else ""
        if system.startswith(TASK_COMPACT):
            return self._compact(user)
        if system.startswith(TASK_SUMMARIZE):
            return self._summarize(user)
        if system.startswith(TASK_ANSWER):
            return self._answer(system, user)
        if system.startswith(TASK_JUDGE):
            return self._judge(user)
        return "OK"

    # compaction: a lossy but schema-complete checkpoint built from the transcript
    def _compact(self, transcript: str) -> str:
        msgs = parse_transcript(transcript)
        users = [m["content"] for m in msgs if m["role"] == "user"]
        assts = [m["content"] for m in msgs if m["role"] == "assistant"]
        all_sents = [s for m in msgs for s in _sentences(re.sub(r"```.*?```", " ", m["content"], flags=re.S))]
        decisions = []
        for s in all_sents:
            if re.search(r"\b(decided|chose|choose|go with|going with|instead of|rather than|because)\b", s, re.I):
                m = re.search(r"\b(because|since)\b(.*)", s, re.I)
                decisions.append({"decision": s, "reason": (m.group(2).strip() if m and m.group(2).strip() else s)})
            if len(decisions) >= 6:
                break
        verbatim = []
        for m in msgs:
            for block in re.findall(r"```[^\n]*\n(.*?)```", m["content"], flags=re.S):
                if block.strip() and len(verbatim) < 8:
                    verbatim.append({"label": f"code block {len(verbatim) + 1}", "content": block})
        completed = [s for s in all_sents if re.search(r"\b(done|fixed|passes|passed|merged|completed|works now)\b", s, re.I)][:5]
        context = " ".join(
            [s for s in all_sents if re.search(r"\b(must|only|cannot|can't|constraint|limit|budget)\b", s, re.I)][:5]
        )
        recent_q = [s for u in users[-3:] for s in _sentences(u) if s.endswith("?")][:3]
        nexts = [s for s in all_sents[-12:] if re.search(r"\b(next|todo|then)\b", s, re.I)][:3]
        last_user = users[-1] if users else ""
        data = {
            "chat_name": "eval-chat",
            "checkpoint_name": "eval-checkpoint",
            "objective": _first(users[0] if users else "", 400),
            "context": context[:800],
            "decisions": decisions,
            "completed": completed,
            "current_step": _first(assts[-1] if assts else last_user),
            "next_steps": [f"Continue with: {_first(last_user)}"] + nexts,
            "open_questions": recent_q,
            "verbatim": verbatim,
            "last_exchange": {"user": last_user, "assistant": assts[-1] if assts else ""},
            "notes_for_next_ai": "",
            "client": "eval",
        }
        return json.dumps(data, indent=1, ensure_ascii=False)

    # free-form summary: intentionally short, as a default "summarise this chat" would be
    def _summarize(self, transcript: str) -> str:
        msgs = parse_transcript(transcript)
        picks = [msgs[0]] if msgs else []
        picks += msgs[2::3]
        if msgs and msgs[-1] not in picks:
            picks.append(msgs[-1])
        out = " ".join(_first(m["content"], 200) for m in picks)
        return ("Summary of the conversation so far: " + out)[:900]

    def _answer(self, system: str, question: str) -> str:
        qt = set(_tokens(question))
        units = [u for u in _sentences(system.split("HANDOVER:", 1)[-1]) if len(u) > 3]
        scored = []
        for i, u in enumerate(units):
            overlap = len(qt & set(_tokens(u)))
            if overlap:
                scored.append((-overlap, i, u))
        if not scored:
            return "The handover does not say."
        scored.sort()
        return " ".join(u for _, _, u in scored[:4])

    def _judge(self, payload: str) -> str:
        try:
            d = json.loads(payload)
        except ValueError:
            return json.dumps({"present": [], "contradictions": 0, "notes": "unparseable"})
        ans = norm(d.get("answer", ""))
        ans_tok = set(_tokens(d.get("answer", "")))
        present = []
        for fact in d.get("key_facts", []):
            nf = norm(fact)
            ft = _tokens(fact)
            ok = nf in ans or (bool(ft) and sum(t in ans_tok for t in ft) / len(ft) >= 0.8)
            present.append(bool(ok))
        wrong = sum(1 for w in d.get("known_wrong", []) if norm(w) and norm(w) in ans)
        return json.dumps({"present": present, "contradictions": wrong, "notes": "fake judge"})


# --------------------------------------------------------------- adapters
def resolve_model_name(provider: str, override: Optional[str]) -> str:
    return override or os.environ.get(MODEL_ENV[provider]) or DEFAULT_MODELS[provider]


def _require_key(provider: str) -> str:
    var = KEY_ENV[provider]
    key = os.environ.get(var)
    if not key:
        raise ModelError(f"--model {provider} needs the {var} environment variable, which is not set")
    return key


def _import(module: str, extra: str):
    try:
        return __import__(module)
    except ImportError:
        raise ModelError(
            f"the {module} package is not installed; run: pip install 'ai-checkpoint[{extra}]'"
        ) from None


class AnthropicModel:
    def __init__(self, model_name: str, api_key: str):
        sdk = _import("anthropic", "anthropic")
        self.name = model_name
        self._client = sdk.Anthropic(api_key=api_key)

    def complete(self, system: str, messages: List[Message]) -> str:
        try:
            r = self._client.messages.create(
                model=self.name, max_tokens=8192, system=system, messages=list(messages)
            )
        except Exception as e:  # SDK raises many types; report one clean error
            raise ModelError(f"anthropic call failed ({self.name}): {e}") from None
        return "".join(getattr(b, "text", "") for b in r.content)


class OpenAIModel:
    def __init__(self, model_name: str, api_key: str):
        sdk = _import("openai", "openai")
        self.name = model_name
        self._client = sdk.OpenAI(api_key=api_key)

    def complete(self, system: str, messages: List[Message]) -> str:
        try:
            r = self._client.chat.completions.create(
                model=self.name, messages=[{"role": "system", "content": system}, *messages]
            )
        except Exception as e:
            raise ModelError(f"openai call failed ({self.name}): {e}") from None
        return r.choices[0].message.content or ""


def make_model(kind: str, model_name: Optional[str] = None) -> Model:
    """Build a model. SDKs are imported here, only for the selected provider."""
    if kind == "fake":
        return FakeModel()
    if kind not in KEY_ENV:
        raise ModelError(f"unknown model {kind!r}; choose one of: {', '.join(MODEL_CHOICES)}")
    key = _require_key(kind)
    name = resolve_model_name(kind, model_name)
    return (AnthropicModel if kind == "anthropic" else OpenAIModel)(name, key)
