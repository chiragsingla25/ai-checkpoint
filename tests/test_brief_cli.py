import re
import subprocess
import sys

import pytest

from ai_checkpoint import Checkpoint, GitStore
from ai_checkpoint.brief import BRIEF_ORDER, EMPTY_MARK, estimate_tokens, render_brief


def _cp(valid, **over):
    cp = Checkpoint.from_dict({**valid, **over})
    cp.checkpoint_id, cp.created_at = "cp-001", "2026-10-07T12:00:00Z"
    return cp


def test_brief_deterministic_ordered_and_framed(valid):
    cp = _cp(valid)
    a, b = render_brief(cp), render_brief(cp)
    assert a == b
    assert a.startswith("You are continuing work from checkpoint cp-001 (forecasting/v1), saved 2026-10-07T12:00:00Z")
    heads = re.findall(r"^## (.+)$", a, re.M)
    assert heads[:len(BRIEF_ORDER)] == list(BRIEF_ORDER)
    assert heads[-1] == "Before you continue"
    tail = a.split("## Before you continue")[1]
    assert "confirm" in tail and "user" in tail


def test_empty_sections_marked_consistently(valid):
    cp = _cp({**valid, "context": "", "decisions": [], "completed": [], "open_questions": [],
              "verbatim": [], "last_exchange": {}, "notes_for_next_ai": ""})
    brief = render_brief(cp)
    assert brief.count(EMPTY_MARK) == 7
    assert [h for h in re.findall(r"^## (.+)$", brief, re.M)][:10] == list(BRIEF_ORDER)


def _extract(brief, label):
    m = re.search(r"\*\*" + re.escape(label) + r"\*\*\n(`{3,})\n(.*?)\n\1(?:\n|$)", brief, re.S)
    return m.group(2)


def test_verbatim_byte_exact(valid):
    nasty = "  lead\n```python\nprint('x')\n````\n\tTab ünï©ode ✓ `inline`\n\n  trail  \n"
    cp = _cp(valid, verbatim=[{"label": "nasty", "content": nasty}, {"label": "plain", "content": "x"}])
    brief = render_brief(cp)
    assert _extract(brief, "nasty") == nasty
    assert _extract(brief, "plain") == "x"
    fence = re.search(r"\*\*nasty\*\*\n(`+)\n", brief).group(1)
    assert len(fence) == 5  # longer than the 4-backtick run inside


def test_last_exchange_word_for_word(valid):
    u = "Why `not` do ```this```?  Two  spaces\nand a line"
    a = "Because — reasons.\n\n  indented"
    brief = render_brief(_cp(valid, last_exchange={"user": u, "assistant": a}))
    assert _extract(brief, "User") == u
    assert _extract(brief, "Assistant") == a


def test_tokens_and_resumed_from_in_listing(store, valid):
    store.save(valid)
    entry = store.list().checkpoints[0]
    assert entry.brief_tokens == estimate_tokens(render_brief(store.get("cp-001")))
    assert entry.brief_tokens > 50


def _cli(*args, home, input=None):
    import os
    env = {**os.environ, "AI_CHECKPOINT_HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run([sys.executable, "-m", "ai_checkpoint", *args], capture_output=True,
                          text=True, env=env, input=input)


def test_cli_roundtrip(tmp_path, valid):
    import json
    home = tmp_path / "h"
    f = tmp_path / "cp.json"
    f.write_text(json.dumps(valid))
    r = _cli("save", "--file", str(f), home=home)
    assert r.returncode == 0 and "cp-001" in r.stdout
    assert "forecasting" in _cli("list", home=home).stdout
    assert "v1" in _cli("list", "--chat", "forecasting", home=home).stdout
    assert "no checkpoints" in _cli("list", "--chat", "other", home=home).stdout
    g = _cli("get", "v1", home=home)
    assert json.loads(g.stdout)["brief_tokens"] > 0
    res = _cli("resume", "cp-001", home=home)
    assert res.stdout == render_brief(GitStore(home).get("cp-001"))


@pytest.mark.parametrize("args", [("resume", "nope"), ("get", "cp-099"), ("save", "--file", "/no/such.json")])
def test_cli_errors_clean(tmp_path, args):
    r = _cli(*args, home=tmp_path / "h")
    assert r.returncode != 0 and r.stderr.startswith("error:") and "Traceback" not in r.stderr


def test_cli_invalid_checkpoint(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text('{"chat_name": "a"}')
    r = _cli("save", "--file", str(f), home=tmp_path / "h")
    assert r.returncode != 0 and "Traceback" not in r.stderr and "checkpoint_name" in r.stderr


@pytest.mark.parametrize("text,kind", [('"str"', "str"), ("null", "NoneType"), ("5", "int"), ("[1]", "list"),
                                       ("[]", "list"), ("true", "bool"), ("1.5", "float")])
def test_cli_save_non_object_json(tmp_path, text, kind):
    r = _cli("save", "--file", "-", home=tmp_path / "h", input=text)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert r.stderr.startswith("error:") and "must contain a JSON object" in r.stderr and kind in r.stderr
    assert not (tmp_path / "h" / "checkpoints").exists() or not list((tmp_path / "h" / "checkpoints").glob("*.json"))


def test_cli_save_deeply_nested_json(tmp_path):
    r = _cli("save", "--file", "-", home=tmp_path / "h", input="[" * 100000 + "]" * 100000)
    assert r.returncode == 1 and "Traceback" not in r.stderr and r.stderr.startswith("error:")


def test_cli_save_empty_stdin(tmp_path):
    r = _cli("save", "--file", "-", home=tmp_path / "h", input="")
    assert r.returncode == 1 and "Traceback" not in r.stderr and r.stderr.startswith("error:")


@pytest.mark.parametrize("bad", ["str", None, 5, [1], b"ab"])
def test_store_save_rejects_non_mapping(store, bad):
    from ai_checkpoint.errors import ValidationError
    with pytest.raises(ValidationError, match="must be an object"):
        store.save(bad)


def test_store_save_accepts_f001_inputs(store, valid):
    class Duck:
        def keys(self):
            return valid.keys()

        def __getitem__(self, k):
            return valid[k]

    assert store.save(list(valid.items())).checkpoint_id
    assert store.save(Duck()).checkpoint_id
    assert store.save(iter(valid.items())).checkpoint_id


def test_store_save_empty_iterable_is_missing_field(store):
    from ai_checkpoint.errors import ValidationError
    with pytest.raises(ValidationError, match="chat_name"):
        store.save([])
