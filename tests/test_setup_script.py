"""Tests for scripts/setup-mac.sh, run against a copy of the repo with a temp HOME."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name != "posix", reason="needs bash"
)


@pytest.fixture(scope="module")
def repo_copy(tmp_path_factory):
    dst = tmp_path_factory.mktemp("repo") / "repo"
    shutil.copytree(
        REPO,
        dst,
        ignore=shutil.ignore_patterns(
            ".venv", ".git", "__pycache__", "*.egg-info", ".pytest_cache", "delivery"
        ),
    )
    return dst


def make_env(tmp_path, with_claude=True):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "claude.log"
    if with_claude:
        stub = bindir / "claude"
        stub.write_text('#!/bin/sh\necho "$@" >> "%s"\n[ "$1 $2" = "mcp remove" ] && exit 1\nexit 0\n' % log)
        stub.chmod(0o755)
    env = dict(os.environ)
    env["HOME"] = str(home)
    # python's dir stays on PATH; the stub dir goes first.
    pydir = str(Path(sys.executable).parent)
    env["PATH"] = "%s:%s:/usr/bin:/bin" % (bindir, pydir)
    env["PYTHON"] = sys.executable
    return env, home, log


def run(repo, env, *args):
    return subprocess.run(
        ["bash", "-euo", "pipefail", str(repo / "scripts" / "setup-mac.sh")] + list(args),
        env=env, capture_output=True, text=True, cwd=str(repo),
    )


def test_help_and_syntax(repo_copy):
    script = repo_copy / "scripts" / "setup-mac.sh"
    assert os.access(script, os.X_OK)
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0
    out = subprocess.run([str(script), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "--dry-run" in out.stdout and "--desktop-config PATH" in out.stdout


def test_dry_run_changes_nothing(repo_copy, tmp_path):
    env, home, log = make_env(tmp_path)
    cfg = tmp_path / "claude_desktop_config.json"
    r = run(repo_copy, env, "--dry-run", "--desktop-config", str(cfg))
    assert r.returncode == 0, r.stderr
    assert "dry-run" in r.stdout
    assert not (repo_copy / ".venv").exists()
    assert not cfg.exists() and list(tmp_path.glob("claude_desktop_config.json*")) == []
    assert not log.exists()


def test_python_too_old(repo_copy, tmp_path):
    env, home, log = make_env(tmp_path)
    stub = tmp_path / "bin" / "python-old"
    stub.write_text('#!/bin/sh\necho 3.9\n')
    stub.chmod(0o755)
    env["PYTHON"] = str(stub)
    cfg = tmp_path / "cfg.json"
    r = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r.returncode != 0 and "3.10" in r.stderr
    assert not (repo_copy / ".venv").exists() and not cfg.exists() and not log.exists()


def test_malformed_config(repo_copy, tmp_path):
    env, home, log = make_env(tmp_path)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{ not json")
    r = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r.returncode != 0 and "not valid JSON" in r.stderr
    assert cfg.read_text() == "{ not json"
    assert not (repo_copy / ".venv").exists()


def test_full_flow(repo_copy, tmp_path):
    env, home, log = make_env(tmp_path)
    cfg = tmp_path / "cfg" / "claude_desktop_config.json"
    r = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r.returncode == 0, r.stdout + r.stderr
    binp = repo_copy / ".venv" / "bin" / "ai-checkpoint-mcp"
    assert binp.exists()
    assert subprocess.run(
        [str(repo_copy / ".venv/bin/python"), "-c", "import mcp, ai_checkpoint"]
    ).returncode == 0
    lines = log.read_text().splitlines()
    assert "mcp remove ai-checkpoint -s local" in lines
    assert "mcp remove ai-checkpoint -s user" in lines
    add = "mcp add -s user ai-checkpoint -e AI_CHECKPOINT_HOME=%s -- %s" % (
        home / ".ai-checkpoint", binp)
    assert add in lines
    assert lines.index("mcp remove ai-checkpoint -s user") < lines.index(add)
    data = json.loads(cfg.read_text())
    assert data == {"mcpServers": {"ai-checkpoint": {
        "command": str(binp), "env": {"AI_CHECKPOINT_HOME": str(home / ".ai-checkpoint")}}}}
    for word in ("Restart", "/mcp", "trial/test-v1"):
        assert word.lower() in r.stdout.lower()

    # second run: idempotent
    before = cfg.read_text()
    r2 = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert cfg.read_text() == before

    # existing config with other content and an older entry
    cfg.write_text(json.dumps({
        "theme": "dark",
        "mcpServers": {"other": {"command": "x"}, "ai-checkpoint": {"command": "old"}},
    }))
    original = cfg.read_text()
    r3 = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r3.returncode == 0, r3.stderr
    baks = list(cfg.parent.glob("claude_desktop_config.json.bak-*"))
    assert len(baks) == 1 and baks[0].read_text() == original
    data = json.loads(cfg.read_text())
    assert data["theme"] == "dark" and data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["ai-checkpoint"]["command"] == str(binp)


def test_no_claude_cli(repo_copy, tmp_path):
    env, home, log = make_env(tmp_path, with_claude=False)
    cfg = tmp_path / "cfg.json"
    r = run(repo_copy, env, "--desktop-config", str(cfg))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped" in r.stdout
    assert json.loads(cfg.read_text())["mcpServers"]["ai-checkpoint"]
