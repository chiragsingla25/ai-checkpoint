import subprocess
import sys

import pytest

from ai_checkpoint import mcp_launcher


def test_missing_mcp_gives_hint_not_traceback():
    code = (
        "import sys; sys.modules['mcp'] = None; sys.modules['pydantic'] = None\n"
        "from ai_checkpoint.mcp_launcher import main; main()"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={"PYTHONPATH": "src", "PATH": ""})
    assert p.returncode == 1
    assert "ai-checkpoint[mcp]" in p.stderr
    assert "Traceback" not in p.stderr


def test_launcher_calls_server_main(monkeypatch):
    pytest.importorskip("mcp")
    import ai_checkpoint.server as server
    called = []
    monkeypatch.setattr(server, "main", lambda: called.append(1))
    mcp_launcher.main()
    assert called == [1]


def test_readme_tester_section_json_and_spec():
    import json
    import re
    from pathlib import Path

    readme = Path(__file__).resolve().parents[1] / "README.md"
    s = readme.read_text(encoding="utf-8")
    sec = s[s.index("## For testers"):s.index("## Quick start")]
    blocks = re.findall(r"```json\n(.*?)```", sec, re.S)
    assert len(blocks) >= 2
    for b in blocks:
        cfg = json.loads(b)["mcpServers"]["ai-checkpoint"]
        assert cfg["command"] == "uvx"
        assert cfg["args"] == ["--from", "ai-checkpoint[mcp] @ git+https://github.com/<owner>/ai-checkpoint",
                               "ai-checkpoint-mcp"]
    for needle in ("astral.sh/uv/install.sh", "install.ps1", "where.exe uvx", "which uvx", "AI_CHECKPOINT_HOME"):
        assert needle in sec
