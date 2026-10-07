import json
import subprocess
import sys
from pathlib import Path

import pytest

import ai_checkpoint
from ai_checkpoint import GitStore, NotFoundError, ValidationError, default_root


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, check=True).stdout


def save(store, valid, **over):
    d = dict(valid)
    d.update(over)
    return store.save(d)


# --- AC1: stdlib only -------------------------------------------------------
def test_core_imports_no_third_party():
    code = (
        "import sys, ai_checkpoint, ai_checkpoint.model, ai_checkpoint.store, "
        "ai_checkpoint.redact, ai_checkpoint.brief;"
        "bad=[m for m in ('mcp','anthropic','openai') if m in sys.modules];"
        "sys.exit(1 if bad else 0)"
    )
    src = str(Path(ai_checkpoint.__file__).parent.parent)
    r = subprocess.run([sys.executable, "-I", "-c", code], env={"PYTHONPATH": src},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- AC2: keys --------------------------------------------------------------
def test_saved_file_has_every_key(store, valid):
    res = store.save(valid)
    data = json.loads(store.path_for(res.checkpoint_id).read_text())
    for key in ["objective", "context", "decisions", "completed", "current_step",
                "next_steps", "open_questions", "verbatim", "last_exchange",
                "notes_for_next_ai", "chat_name", "checkpoint_name", "checkpoint_id",
                "created_at", "client", "resumed_from"]:
        assert key in data
    assert data["created_at"].endswith("Z") and "T" in data["created_at"]
    assert data["decisions"] == [{"decision": "Use Prophet", "reason": "handles seasonality"}]
    assert data["last_exchange"] == {"user": "go on", "assistant": "ok"}


def test_minimal_save_fills_defaults(store):
    res = store.save({"chat_name": "c", "checkpoint_name": "n", "objective": "o",
                      "current_step": "s", "next_steps": ["a"]})
    data = json.loads(store.path_for(res.checkpoint_id).read_text())
    assert data["client"] == "unknown" and data["resumed_from"] is None
    assert data["verbatim"] == [] and data["last_exchange"] == {"user": "", "assistant": ""}


# --- AC3: root --------------------------------------------------------------
def test_default_root_and_env(isolated_home, monkeypatch, tmp_path):
    assert default_root() == isolated_home / ".ai-checkpoint"
    monkeypatch.setenv("AI_CHECKPOINT_HOME", str(tmp_path / "elsewhere"))
    assert default_root() == tmp_path / "elsewhere"
    assert GitStore().root == tmp_path / "elsewhere"


def test_env_home_save_writes_only_there(isolated_home, monkeypatch, tmp_path, valid):
    target = tmp_path / "elsewhere"
    monkeypatch.setenv("AI_CHECKPOINT_HOME", str(target))
    GitStore().save(valid)
    assert (target / "checkpoints" / "cp-001.json").is_file()
    assert list(isolated_home.iterdir()) == []


# --- AC4: git ---------------------------------------------------------------
def test_one_commit_per_save(store, valid, root):
    r1 = save(store, valid)
    r2 = save(store, valid, checkpoint_name="v2")
    log = git(root, "log", "--format=%s").splitlines()
    assert log == ["checkpoint: cp-002 forecasting/v2", "checkpoint: cp-001 forecasting/v1"]
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "rev-parse", "HEAD").strip() == r2.commit
    assert r1.commit != r2.commit
    assert (root / ".git").is_dir()


# --- AC5: ids ---------------------------------------------------------------
def test_ids_sequential_and_never_reused(store, valid):
    assert [save(store, valid).checkpoint_id for _ in range(2)] == ["cp-001", "cp-002"]
    store.path_for("cp-002").unlink()
    assert save(store, valid).checkpoint_id == "cp-003"


def test_ids_not_reused_when_all_deleted(store, valid):
    save(store, valid)
    store.path_for("cp-001").unlink()
    assert save(store, valid).checkpoint_id == "cp-002"


# --- AC6: immutability ------------------------------------------------------
def test_same_name_creates_new_id_and_resolves_newest(store, valid):
    a = save(store, valid, objective="first")
    before = store.path_for(a.checkpoint_id).read_bytes()
    b = save(store, valid, objective="second")
    assert a.checkpoint_id != b.checkpoint_id
    assert store.path_for(a.checkpoint_id).read_bytes() == before
    assert store.get("v1").objective == "second"
    assert store.get("forecasting/v1").checkpoint_id == b.checkpoint_id
    assert store.get(a.checkpoint_id).objective == "first"


# --- AC7: resolution --------------------------------------------------------
def test_resolve_forms(store, valid):
    for i in range(7):
        save(store, valid, checkpoint_name=f"n{i}")
    assert store.resolve("cp-007") == "cp-007"
    assert store.resolve("cp-7") == "cp-007"
    assert store.resolve("n2") == "cp-003"
    assert store.resolve("forecasting/n2") == "cp-003"


def test_unknown_ref_names_ref(store, valid):
    save(store, valid)
    for ref in ("nope", "chat/nope", "cp-099"):
        with pytest.raises(NotFoundError) as e:
            store.get(ref)
        assert ref in str(e.value)


def test_bare_name_in_multiple_chats_resolves_newest(store, valid):
    a = save(store, valid, chat_name="alpha", checkpoint_name="final")
    b = save(store, valid, chat_name="beta", checkpoint_name="final")
    assert store.resolve("final") == b.checkpoint_id
    assert store.resolve("alpha/final") == a.checkpoint_id
    c = save(store, valid, chat_name="alpha", checkpoint_name="final")
    assert store.resolve("final") == c.checkpoint_id


# --- AC8: validation --------------------------------------------------------
@pytest.mark.parametrize("mutate,field", [
    (lambda d: d.pop("objective"), "objective"),
    (lambda d: d.pop("current_step"), "current_step"),
    (lambda d: d.pop("next_steps"), "next_steps"),
    (lambda d: d.update(next_steps=[]), "next_steps"),
    (lambda d: d.update(next_steps="do it"), "next_steps"),
    (lambda d: d.update(objective=5), "objective"),
    (lambda d: d.update(objective="  "), "objective"),
    (lambda d: d.update(verbatim=[{"content": "x"}]), "verbatim[0].label"),
    (lambda d: d.update(verbatim=[{"label": "x"}]), "verbatim[0].content"),
    (lambda d: d.update(verbatim="x"), "verbatim"),
    (lambda d: d.update(decisions=[{"decision": "x"}]), "decisions[0].reason"),
    (lambda d: d.update(completed="done"), "completed"),
    (lambda d: d.update(completed=[1]), "completed[0]"),
    (lambda d: d.update(last_exchange="hi"), "last_exchange"),
    (lambda d: d.update(chat_name="a/b"), "chat_name"),
    (lambda d: d.update(checkpoint_name="cp-004"), "checkpoint_name"),
    (lambda d: d.update(checkpoint_name="a\nb"), "checkpoint_name"),
    (lambda d: d.update(client=3), "client"),
])
def test_validation_rejects_and_writes_nothing(store, valid, root, mutate, field):
    mutate(valid)
    with pytest.raises(ValidationError) as e:
        store.save(valid)
    assert e.value.field == field and field in str(e.value)
    assert not root.exists() or not list((root / "checkpoints").glob("*"))
    if (root / ".git").exists():
        assert subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True).returncode != 0


def test_validation_failure_after_good_save_adds_no_commit(store, valid, root):
    save(store, valid)
    with pytest.raises(ValidationError):
        save(store, valid, next_steps=[])
    assert len(git(root, "log", "--oneline").splitlines()) == 1
    assert git(root, "status", "--porcelain") == ""


# --- AC9: resumed_from ------------------------------------------------------
def test_resumed_from(store, valid, root):
    a = save(store, valid)
    b = save(store, valid, checkpoint_name="v2", resumed_from="forecasting/v1")
    assert store.get(b.checkpoint_id).resumed_from == a.checkpoint_id
    c = save(store, valid, checkpoint_name="v3", resumed_from="cp-002")
    assert c.checkpoint.resumed_from == "cp-002"
    with pytest.raises(ValidationError) as e:
        save(store, valid, checkpoint_name="v4", resumed_from="ghost")
    assert e.value.field == "resumed_from" and "ghost" in str(e.value)
    assert len(git(root, "log", "--oneline").splitlines()) == 3


# --- AC10: redaction --------------------------------------------------------
SECRETS = [
    "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    "sk-proj1234567890abcdefghijklmnop",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "AKIAIOSFODNN7EXAMPLE",
    "Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
    "api_key=Zx81hQpLm29",
    "token=abcd1234efgh",
    "password=hunter2hunter2",
    'password = "correct horse battery"',
    '"password": "s3cretValue"',
]
PLAIN_CODE = (
    "def f(x):\n    return x * 2  # keep: max_tokens=1000, token=get_token()\n"
    "Authorization header uses Bearer authentication.\n"
    "ask-me task-force risk-assessment-framework-for-everything\n"
    "tabs\t and unicode: café ✓\n"
)


def test_redaction_end_to_end(store, valid, root):
    valid["verbatim"] = [{"label": "code", "content": PLAIN_CODE + "\n".join(SECRETS)}]
    valid["context"] = "key is " + SECRETS[0]
    valid["last_exchange"] = {"user": SECRETS[2], "assistant": "ok " + SECRETS[4]}
    valid["notes_for_next_ai"] = SECRETS[5]
    valid["objective"] = f"use {SECRETS[1]}"
    valid["checkpoint_name"] = "with-" + SECRETS[3]
    res = store.save(valid)
    on_disk = store.path_for(res.checkpoint_id).read_text()
    history = git(root, "log", "-p", "--format=fuller")
    for text in (on_disk, history):
        for s in SECRETS:
            secret_part = s.split("=")[-1].strip('" ') if "=" in s or ":" in s else s.split()[-1]
            assert secret_part not in text, s
        assert "[REDACTED]" in text
    content = json.loads(on_disk)["verbatim"][0]["content"]
    assert content.startswith(PLAIN_CODE)  # ordinary text/code byte-for-byte
    assert "password = \"[REDACTED]\"" in content
    assert "api_key=[REDACTED]" in content


def test_redaction_idempotent_and_marker_survives():
    from ai_checkpoint import redact_text
    once = redact_text("token=abcd1234efgh and Bearer abcd1234efgh")
    assert redact_text(once) == once


# --- AC11: listing ----------------------------------------------------------
def test_list_empty_and_missing_store(store, root):
    assert not root.exists()
    assert len(store.list()) == 0 and store.list().to_dict()["chats"] == []
    root.mkdir()
    assert len(store.list()) == 0


def test_list_newest_first_grouped_filtered(store, valid):
    save(store, valid, chat_name="a", checkpoint_name="one")
    save(store, valid, chat_name="b", checkpoint_name="two", client="chatgpt")
    save(store, valid, chat_name="a", checkpoint_name="three", resumed_from="a/one")
    lst = store.list()
    assert [e.checkpoint_id for e in lst.checkpoints] == ["cp-003", "cp-002", "cp-001"]
    assert list(lst.chats) == ["a", "b"]
    assert [e.checkpoint_name for e in lst.chats["a"]] == ["three", "one"]
    e = lst.checkpoints[0]
    assert (e.chat_name, e.client, e.resumed_from) == ("a", "claude-code", "cp-001")
    assert e.created_at.endswith("Z") and e.brief_tokens > 0
    only_b = store.list(chat_name="b")
    assert [e.checkpoint_id for e in only_b.checkpoints] == ["cp-002"]
    assert only_b.checkpoints[0].client == "chatgpt"
    assert set(lst.to_dict()["checkpoints"][0]) == {
        "id", "chat_name", "checkpoint_name", "created_at", "client", "resumed_from", "brief_tokens"}
    assert store.list("nope").checkpoints == []


def test_brief_tokens_uses_brief_hook(store, valid, monkeypatch):
    from ai_checkpoint import brief
    save(store, valid)
    monkeypatch.setattr(brief, "render_brief", lambda cp: "x" * 400)
    assert store.list().checkpoints[0].brief_tokens == 100


def test_works_without_git_identity(store, valid, root):
    save(store, valid)  # conftest sets GIT_CONFIG_GLOBAL=/dev/null, no user.name anywhere
    assert "AI Checkpoint" in git(root, "log", "--format=%an")
