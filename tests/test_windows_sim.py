"""Windows-simulation tests. These run on Linux/macOS and only SIMULATE Windows
(hidden fcntl, fake msvcrt, CRLF files, autocrlf git config, cp1252 console).
Real-Windows verification is done by the testers."""
import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

from ai_checkpoint import GitStore
from ai_checkpoint.errors import NotFoundError, StoreError
from ai_checkpoint.store import default_root

UNI = "café ✓ 日本"


class FakeMsvcrt(types.ModuleType):
    LK_LOCK, LK_NBLCK, LK_UNLCK = 1, 2, 0

    def __init__(self):
        super().__init__("msvcrt")
        self.calls = []

    def locking(self, fd, mode, nbytes):
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        self.calls.append((fd, mode, nbytes, pos))


@pytest.fixture
def win(monkeypatch):
    fake = FakeMsvcrt()
    monkeypatch.setitem(sys.modules, "fcntl", None)
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    return fake


def test_msvcrt_lock_used_and_unlocked(store, valid, win):
    r = store.save(valid)
    modes = [c[1] for c in win.calls]
    assert modes == [win.LK_LOCK, win.LK_UNLCK]
    lock, unlock = win.calls
    assert lock[0] == unlock[0] and lock[2] == unlock[2]
    assert lock[3] == 0 and unlock[3] == 0  # fixed range from offset 0
    assert store.path_for(r.checkpoint_id).is_file()
    assert store._git("log", "--oneline").stdout.count("\n") == 1


def test_msvcrt_unlock_on_failure(store, valid, win, monkeypatch):
    real = store._git

    def boom(*args, **kw):
        if "commit" in args:
            raise StoreError("commit failed")
        return real(*args, **kw)

    monkeypatch.setattr(store, "_git", boom)
    with pytest.raises(StoreError):
        store.save(valid)
    assert win.calls[-1][1] == win.LK_UNLCK
    assert not list(store.checkpoint_dir.glob("cp-*.json"))


def test_no_lock_modules_noop(store, valid, monkeypatch):
    monkeypatch.setitem(sys.modules, "fcntl", None)
    monkeypatch.setitem(sys.modules, "msvcrt", None)
    store.save(valid)
    assert len(store.list()) == 1
    assert store.get("forecasting/v1").chat_name == "forecasting"
    assert store.get("v1").checkpoint_name == "v1"


def test_fcntl_concurrent_saves_distinct_ids(root, valid):
    GitStore(root)._ensure_repo()
    ids, errs = [], []

    def run(i):
        d = dict(valid, checkpoint_name=f"n{i}")
        try:
            ids.append(GitStore(root).save(d).checkpoint_id)
        except Exception as e:  # pragma: no cover
            errs.append(e)

    ts = [threading.Thread(target=run, args=(i,)) for i in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    assert sorted(ids) == [f"cp-00{i}" for i in range(1, 6)]


def test_utf8_no_crlf_roundtrip(store, valid):
    valid["context"] = UNI
    r = store.save(valid)
    raw = store.path_for(r.checkpoint_id).read_bytes()
    assert b"\r\n" not in raw
    assert UNI.encode("utf-8") in raw
    assert store.get(r.checkpoint_id).context == UNI


def test_crlf_file_still_loads(store, valid):
    r = store.save(valid)
    p = store.path_for(r.checkpoint_id)
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert b"\r\n" in p.read_bytes()
    assert len(store.list()) == 1
    assert store.get(r.checkpoint_id).objective == valid["objective"]
    from ai_checkpoint.brief import render_brief
    assert render_brief(store.get("forecasting/v1"))


def test_autocrlf_global_config_ignored(store, valid, tmp_path, monkeypatch):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[core]\n\tautocrlf = true\n\tsafecrlf = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    store.save(valid)
    store.save(dict(valid, checkpoint_name="v2"))
    assert len(store.list()) == 2


def test_default_root(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_CHECKPOINT_HOME", raising=False)
    assert default_root() == Path.home() / ".ai-checkpoint"
    monkeypatch.setenv("AI_CHECKPOINT_HOME", "")
    assert default_root() == Path.home() / ".ai-checkpoint"
    monkeypatch.setenv("AI_CHECKPOINT_HOME", str(tmp_path / "x"))
    assert default_root() == Path(str(tmp_path / "x"))


def test_backslash_ref_is_plain_name(store, valid):
    store.save(valid)
    with pytest.raises(NotFoundError):
        store.resolve("chat\\name")
    with pytest.raises(NotFoundError):
        store.resolve("forecasting\\v1")
    assert store.resolve("forecasting/v1") == "cp-001"


def _cli(*args, env_extra=None, **kw):
    env = dict(os.environ, **(env_extra or {}))
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "ai_checkpoint", *args],
                          capture_output=True, env=env, **kw)


@pytest.mark.parametrize("cmd", ["get", "resume"])
def test_cli_utf8_under_cp1252(store, valid, root, cmd):
    valid["context"] = UNI
    store.save(valid)
    p = _cli(cmd, "forecasting/v1", env_extra={
        "PYTHONIOENCODING": "cp1252", "AI_CHECKPOINT_HOME": str(root)})
    assert p.returncode == 0, p.stderr
    assert b"UnicodeEncodeError" not in p.stderr
    assert "日本".encode("utf-8") in p.stdout


def test_git_missing_is_store_error(store, valid, tmp_path, monkeypatch):
    empty = tmp_path / "emptybin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(StoreError, match="git"):
        store.save(valid)


def test_git_missing_mcp_tool_error(store, valid, tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    import asyncio
    from ai_checkpoint.server import create_server
    empty = tmp_path / "emptybin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    srv = create_server(store)

    async def go():
        return await srv.call_tool("save_checkpoint", dict(valid))

    with pytest.raises(Exception) as ei:
        asyncio.run(go())
    assert "git" in str(ei.value)


def test_cli_error_with_surrogate_arg_still_prints(tmp_path):
    """Regression: _force_utf8 must keep stderr's error handler, so an error
    message containing a lone surrogate (non-UTF-8 argv bytes) is still shown."""
    env = {**os.environ, "AI_CHECKPOINT_HOME": str(tmp_path / "home")}
    r = subprocess.run([sys.executable, "-m", "ai_checkpoint", "save", "--file", b"\xff.json"],
                       capture_output=True, env=env)
    assert r.returncode == 1
    assert b"cannot read" in r.stderr
    assert b"lost sys.stderr" not in r.stderr


def test_cli_stdin_not_reencoded_under_cp1252(tmp_path, valid):
    """Regression: stdin must decode exactly as before (console encoding), not be forced to UTF-8."""
    import json
    payload = dict(valid, chat_name="w", checkpoint_name="café", context="naïve €")
    data = json.dumps(payload, ensure_ascii=False).encode("cp1252")
    home = tmp_path / "home"
    r = _cli("save", "--file", "-", input=data,
             env_extra={"PYTHONIOENCODING": "cp1252", "AI_CHECKPOINT_HOME": str(home)})
    assert r.returncode == 0, r.stderr
    g = _cli("get", "w/café", env_extra={"PYTHONIOENCODING": "utf-8", "AI_CHECKPOINT_HOME": str(home)})
    assert g.returncode == 0, g.stderr
    assert json.loads(g.stdout.decode("utf-8"))["checkpoint_name"] == "café"


def test_msvcrt_retry_sleeps_between_attempts(store, valid, win, monkeypatch):
    import ai_checkpoint.store as st
    n = {"c": 0}
    real = win.locking

    def flaky(fd, mode, nbytes):
        if mode == win.LK_LOCK and n["c"] < 2:
            n["c"] += 1
            raise OSError("busy")
        return real(fd, mode, nbytes)

    win.locking = flaky
    sleeps = []
    monkeypatch.setattr(st.time, "sleep", lambda s: sleeps.append(s))
    store.save(valid)
    assert len(sleeps) == 2 and all(s > 0 for s in sleeps)
