"""F-002: bundle storage, manifest, events log, compatibility (docs/DESIGN-v2.md)."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_checkpoint import GitStore
from ai_checkpoint import bundle
from ai_checkpoint.errors import StoreError
from disk import cp_path, tree_bytes

FIXTURES = Path(__file__).parent / "fixtures"
FILES = ["manifest.json", "plan.json", "decisions.jsonl", "facts.jsonl", "workspace.json",
         "user_turns.jsonl", "open_questions.json", "brief.md", "core.json"]


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, check=True).stdout


@pytest.fixture
def store(tmp_path):
    return GitStore(tmp_path / "store")


def save(store, valid, **over):
    return store.save({**valid, **over})


def test_save_creates_bundle_and_one_commit(store, valid):
    r = save(store, valid)
    d = store.root / "chats" / bundle.chat_folder("forecasting") / "checkpoints" / "cp-001"
    assert d.is_dir()
    for f in FILES:
        assert (d / f).is_file(), f
    assert (d / "verbatim").is_dir()
    assert not (store.root / "checkpoints" / "cp-001.json").exists()
    assert git(store.root, "rev-list", "--count", "HEAD").strip() == "1"
    changed = sorted(git(store.root, "show", "--name-only", "--format=", "HEAD").split())
    base = "chats/" + bundle.chat_folder("forecasting")
    assert changed == sorted([f"{base}/chat.json", f"{base}/events.jsonl"] +
                             [f"{base}/checkpoints/cp-001/{f}" for f in FILES] +
                             [f"{base}/checkpoints/cp-001/verbatim/01-model.txt",
                              f"{base}/checkpoints/cp-001/verbatim/.keep"])
    save(store, valid, checkpoint_name="v2")
    changed = git(store.root, "show", "--name-only", "--format=", "HEAD").split()
    assert not any(c.endswith("chat.json") for c in changed)
    assert all("cp-002" in c or c.endswith("events.jsonl") for c in changed)
    assert r.checkpoint_id == "cp-001"


def test_manifest_hashes(store, valid):
    r = save(store, valid)
    d = cp_path(store, r.checkpoint_id)
    m = json.loads((d / "manifest.json").read_text())
    assert m["id"] == "cp-001" and m["resumed_from"] is None and m["client"] == "claude-code"
    assert m["created_at"] and m["version"] == 2
    on_disk = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()} - {"manifest.json"}
    assert set(m["files"]) == on_disk
    for rel, h in m["files"].items():
        assert hashlib.sha256((d / rel).read_bytes()).hexdigest() == h


TRICKY = "a\ttab  \r\nCRLF `code` ``` 日本 café  \n  trailing   "


def test_verbatim_exact_and_duplicates(store, valid):
    valid["verbatim"] = [{"label": "Same Label", "content": TRICKY},
                         {"label": "Same Label", "content": "second"},
                         {"label": "???", "content": "x"}]
    r = save(store, valid)
    d = cp_path(store, r.checkpoint_id) / "verbatim"
    files = sorted(p.name for p in d.iterdir())
    assert files == [".keep", "01-same-label.txt", "02-same-label.txt", "03-item.txt"]
    assert (d / files[1]).read_bytes() == TRICKY.encode("utf-8")
    assert (d / files[2]).read_bytes() == b"second"
    got = store.get("cp-001")
    assert [v.content for v in got.verbatim] == [TRICKY, "second", "x"]


def test_events_appended_once_per_save(store, valid):
    save(store, valid)
    ev = store.root / "chats" / bundle.chat_folder("forecasting") / "events.jsonl"
    first = ev.read_bytes()
    assert first.count(b"\n") == 1
    save(store, valid, checkpoint_name="v2", resumed_from="cp-001")
    second = ev.read_bytes()
    assert second.startswith(first) and second.count(b"\n") == 2
    lines = [json.loads(l) for l in second.splitlines()]
    assert [(l["seq"], l["type"], l["checkpoint_id"]) for l in lines] == [
        (1, "checkpoint_saved", "cp-001"), (2, "checkpoint_saved", "cp-002")]
    assert lines[1]["resumed_from"] == "cp-001" and lines[0]["next_action"] == "t-1"


def test_chat_folder_naming():
    assert bundle.chat_folder("Forecast") == bundle.chat_folder(" forecast ")
    assert bundle.chat_folder("My Chat") != bundle.chat_folder("my-chat")
    assert bundle.chat_folder("My Chat").startswith("my-chat-")
    assert bundle.chat_folder("預測").startswith("chat-")
    assert bundle.chat_folder("x" * 100).startswith("x" * 40 + "-")


def test_chat_json_and_collision_suffix(store, valid):
    save(store, valid, chat_name="Forecast")
    save(store, valid, chat_name="forecast", checkpoint_name="b")
    base = store.root / "chats" / bundle.chat_folder("forecast")
    assert json.loads((base / "chat.json").read_text())["chat_name"] == "Forecast"
    assert len(list((base / "checkpoints").iterdir())) == 2
    # a foreign folder squatting on the next chat's name forces a suffix
    squat = store.root / "chats" / bundle.chat_folder("other")
    squat.mkdir(parents=True)
    (squat / "chat.json").write_text(json.dumps({"chat_name": "x", "key": "x"}))
    save(store, valid, chat_name="other")
    assert (store.root / "chats" / (bundle.chat_folder("other") + "-2") / "chat.json").is_file()


def test_mixed_flat_and_bundles(store, valid):
    store._ensure_repo()
    old = json.loads((FIXTURES / "old_format_cp.json").read_text())
    (store.checkpoint_dir / "cp-003.json").write_text(json.dumps(old), encoding="utf-8")
    flat_before = (store.checkpoint_dir / "cp-003.json").read_bytes()
    a = save(store, valid)
    assert a.checkpoint_id == "cp-004"
    b = save(store, valid, chat_name="legacy-chat", checkpoint_name="old-format")
    assert b.checkpoint.checkpoint_name == "old-format (1)" and b.checkpoint_id == "cp-005"
    assert store.get("cp-003").objective == "Finish the demand forecast"
    assert store.resolve("legacy-chat/old-format") == "cp-003"
    assert store.resolve("old-format (1)") == "cp-005"
    assert store.resolve("forecasting/v1") == "cp-004"
    assert store.get("cp-004").next_steps == valid["next_steps"]
    ids = [e.checkpoint_id for e in store.list().checkpoints]
    assert ids == ["cp-005", "cp-004", "cp-003"]
    assert [e.checkpoint_id for e in store.list("legacy-chat").checkpoints] == ["cp-005", "cp-003"]
    assert (store.checkpoint_dir / "cp-003.json").read_bytes() == flat_before


def test_ids_use_git_history_for_bundles(store, valid):
    save(store, valid)
    save(store, valid, checkpoint_name="v2")
    shutil.rmtree(cp_path(store, "cp-002"))
    assert save(store, valid, checkpoint_name="v3").checkpoint_id == "cp-003"


def test_golden_old_format_resume(store):
    from ai_checkpoint.brief import render_brief
    store._ensure_repo()
    shutil.copy(FIXTURES / "old_format_cp.json", store.checkpoint_dir / "cp-003.json")
    h = hashlib.sha256((store.checkpoint_dir / "cp-003.json").read_bytes()).hexdigest()
    golden = (FIXTURES / "old_format_brief.golden.md").read_bytes()
    assert render_brief(store.get("cp-003")).encode("utf-8") == golden
    from ai_checkpoint.server import create_server
    srv = create_server(store)
    import asyncio
    from test_server import _text
    text = _text(asyncio.run(srv.call_tool("resume_checkpoint", {"ref": "cp-003"})))
    assert text.encode("utf-8") == golden
    store.save({"chat_name": "z", "checkpoint_name": "n", "objective": "o",
                "current_step": "s", "next_steps": ["a"]})
    assert hashlib.sha256((store.checkpoint_dir / "cp-003.json").read_bytes()).hexdigest() == h


def test_secrets_nowhere_in_store(store, valid):
    secrets = ["sk-ant-api03-abcdefghijklmnop1234", "password=hunter2hunter2",
               "Bearer abcdefghij1234567890", "https://user:s3cretpass@host.example/x"]
    valid["objective"] = "use " + secrets[0]
    valid["context"] = secrets[1]
    valid["verbatim"] = [{"label": "k " + secrets[0], "content": secrets[2] + "\n" + secrets[3]}]
    valid["last_exchange"] = {"user": secrets[1], "assistant": secrets[3]}
    valid["next_steps"] = ["User's plan: " + secrets[2]]
    valid["checkpoint_name"] = "n-" + secrets[0]
    valid["open_questions"] = [secrets[1]]
    save(store, valid)
    blob = b""
    for p in store.root.rglob("*"):
        if p.is_file() and ".git" not in p.relative_to(store.root).parts:
            blob += p.read_bytes()
    blob += git(store.root, "log", "-p", "--format=fuller").encode()
    for needle in (b"sk-ant-api03-abcdefghijklmnop1234", b"hunter2hunter2",
                   b"abcdefghij1234567890", b"s3cretpass"):
        assert needle not in blob, needle
    assert b"[REDACTED]" in blob


def test_commit_failure_rolls_back_first_save(store, valid, monkeypatch):
    real = store._git

    def boom(*a, **kw):
        if "commit" in a:
            raise StoreError("commit failed")
        return real(*a, **kw)

    monkeypatch.setattr(store, "_git", boom)
    with pytest.raises(StoreError):
        save(store, valid)
    assert not list((store.root / "chats").rglob("*"))
    monkeypatch.undo()
    assert save(store, valid).checkpoint_id == "cp-001"


def test_commit_failure_restores_events(store, valid, monkeypatch):
    save(store, valid)
    ev = store.root / "chats" / bundle.chat_folder("forecasting") / "events.jsonl"
    before = ev.read_bytes()
    real = store._git

    def boom(*a, **kw):
        if "commit" in a:
            raise StoreError("commit failed")
        return real(*a, **kw)

    monkeypatch.setattr(store, "_git", boom)
    with pytest.raises(StoreError):
        save(store, valid, checkpoint_name="v2")
    assert ev.read_bytes() == before
    assert not (ev.parent / "checkpoints" / "cp-002").exists()
    assert git(store.root, "status", "--porcelain") == ""


def test_corrupt_bundle_skipped(store, valid):
    save(store, valid)
    save(store, valid, checkpoint_name="v2")
    (cp_path(store, "cp-002") / "plan.json").write_text("{not json")
    assert [e.checkpoint_id for e in store.list().checkpoints] == ["cp-001"]
    with pytest.raises(Exception):
        store.get("cp-002")
    assert store.get("cp-001").objective == valid["objective"]
    (cp_path(store, "cp-001") / "manifest.json").write_text("[]")
    assert len(store.list()) == 0


def test_flat_view_roundtrip_user_plan(store, valid):
    valid["next_steps"] = ["User's plan: do A", "ai step"]
    r = save(store, valid)
    plan = json.loads((cp_path(store, r.checkpoint_id) / "plan.json").read_text())
    assert [(t["id"], t["from"], t["quote"], t["order"]) for t in plan["tasks"]] == [
        ("t-1", "user", "do A", 10), ("t-2", "ai", None, 20)]
    assert plan["next_action"] == {"task_id": "t-1", "text": "do A"}
    assert store.get("cp-001").next_steps == valid["next_steps"]


def test_verbatim_dir_survives_when_empty(store, valid):
    valid["verbatim"] = []
    r = save(store, valid)
    d = cp_path(store, r.checkpoint_id)
    assert (d / "verbatim" / ".keep").read_bytes() == b""
    m = json.loads((d / "manifest.json").read_text())
    assert "verbatim/.keep" in m["files"] and m["verbatim"] == []
    assert "verbatim/.keep" in git(store.root, "ls-files")


@pytest.mark.parametrize("step", ["User's plan:foo", "User's plan:  two spaces",
                                  "User's plan: normal", "User's plan:\tx"])
def test_user_plan_steps_round_trip_byte_for_byte(store, valid, step):
    from ai_checkpoint.brief import render_brief
    valid["next_steps"] = [step, "ai step"]
    r = save(store, valid)
    assert store.get(r.checkpoint_id).next_steps == [step, "ai step"]
    assert step in render_brief(store.get(r.checkpoint_id))
    plan = json.loads((cp_path(store, r.checkpoint_id) / "plan.json").read_text())
    assert plan["tasks"][0]["from"] == "user"
    assert plan["tasks"][0]["text"] == step[len("User's plan:"):].lstrip()
