"""F-001: rejected alternatives on decisions (how far each one got)."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from disk import cp_path, disk_text, remove_cp, tree_bytes

from ai_checkpoint import GitStore
from ai_checkpoint.brief import render_brief
from ai_checkpoint.errors import ValidationError
from ai_checkpoint.model import Checkpoint

FIXTURES = Path(__file__).parent / "fixtures"


def _with_rejected(valid, rejected):
    valid["decisions"] = [{"decision": "Use Prophet", "reason": "seasonality", "rejected": rejected}]
    return valid


GOOD = [
    {"option": "hooks", "how_far": "prototyped", "note": "too brittle"},
    {"option": "daemon", "how_far": "built_then_removed"},
    {"option": "cron", "how_far": "discussed"},
]


def test_rejected_roundtrips_unchanged(valid):
    cp = Checkpoint.from_dict(_with_rejected(valid, GOOD))
    assert cp.to_dict()["decisions"][0]["rejected"] == GOOD
    again = Checkpoint.from_dict(cp.to_dict())
    assert again.to_dict() == cp.to_dict()


@pytest.mark.parametrize("variant", ["absent", None, []])
def test_rejected_absent_null_empty_gives_empty_list(valid, variant):
    if variant != "absent":
        valid["decisions"][0]["rejected"] = variant
    cp = Checkpoint.from_dict(valid)
    assert cp.decisions[0].rejected == []
    d = cp.to_dict()
    assert "rejected" not in d["decisions"][0]  # empty list is not written; old files stay as they were
    again = Checkpoint.from_dict(d)
    assert again.decisions[0].rejected == [] and again.to_dict() == d


@pytest.mark.parametrize(
    "bad,field",
    [
        ([{"option": "x", "how_far": "tried"}], "decisions[0].rejected[0].how_far"),
        ([{"option": "x"}], "decisions[0].rejected[0].how_far"),
        ([{"option": "", "how_far": "discussed"}], "decisions[0].rejected[0].option"),
        ([{"option": "  ", "how_far": "discussed"}], "decisions[0].rejected[0].option"),
        ([{"how_far": "discussed"}], "decisions[0].rejected[0].option"),
        ("hooks", "decisions[0].rejected"),
        ({"option": "x", "how_far": "discussed"}, "decisions[0].rejected"),
        (["hooks"], "decisions[0].rejected[0]"),
        ([{"option": "x", "how_far": "discussed", "note": 5}], "decisions[0].rejected[0].note"),
    ],
)
def test_rejected_validation_names_field(valid, bad, field):
    with pytest.raises(ValidationError) as ei:
        Checkpoint.from_dict(_with_rejected(valid, bad))
    assert ei.value.field == field


def test_brief_lists_rejected_in_words(valid):
    brief = render_brief(Checkpoint.from_dict(_with_rejected(valid, GOOD)))
    assert "Rejected: hooks (prototyped) - too brittle" in brief
    assert "Rejected: daemon (built, then removed)" in brief
    assert "Rejected: cron (discussed)" in brief
    # listed under its decision, before the next section
    assert brief.index("Use Prophet") < brief.index("Rejected: hooks") < brief.index("## Completed so far")


def test_save_redacts_secrets_in_option_and_note(store, valid):
    _with_rejected(valid, [{
        "option": "use key sk-ant-api03-abcdefghijklmnop1234",
        "how_far": "prototyped",
        "note": "had token=abcd1234efgh in the URL",
    }])
    res = store.save(valid)
    raw = disk_text(store, res.checkpoint_id)
    assert "sk-ant-api03-abcdefghijklmnop1234" not in raw
    assert "abcd1234efgh" not in raw
    r = store.get(res.checkpoint_id).decisions[0].rejected[0]
    assert "sk-ant" not in r.option and "abcd1234efgh" not in r.note


def test_save_schema_documents_rejected():
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server

    tools = asyncio.run(create_server().list_tools())
    t = [x for x in tools if x.name == "save_checkpoint"][0]
    schema = getattr(t, "inputSchema", None) or t.input_schema
    defs = schema["$defs"]
    dec = defs["DecisionIn"]["properties"]["rejected"]
    assert "rejected" in dec["description"] and "how_far" in dec["description"]
    rej = defs["RejectedIn"]
    assert set(rej["required"]) == {"option", "how_far"}
    assert rej["properties"]["how_far"]["enum"] == ["discussed", "prototyped", "built_then_removed"]
    for v in ("discussed", "prototyped", "built_then_removed"):
        assert v in rej["properties"]["how_far"]["description"]


def test_save_via_mcp_accepts_and_rejects_how_far(root, valid):
    pytest.importorskip("mcp")
    from mcp.server.mcpserver.exceptions import ToolError
    from ai_checkpoint.server import create_server

    server = create_server(GitStore(root))
    asyncio.run(server.call_tool("save_checkpoint", _with_rejected(valid, GOOD)))
    assert GitStore(root).get("cp-001").to_dict()["decisions"][0]["rejected"] == GOOD
    with pytest.raises(Exception):
        asyncio.run(server.call_tool(
            "save_checkpoint", _with_rejected(dict(valid, checkpoint_name="v2"), [{"option": "x", "how_far": "tried"}])
        ))


# ------------------------------------------------ old-format backward compatibility
def _install_old_fixture(home):
    """Place the pre-change file where an old store would have it (no git needed to read)."""
    store = GitStore(home)
    store.checkpoint_dir.mkdir(parents=True)
    store.path_for("cp-003").write_text((FIXTURES / "old_format_cp.json").read_text(encoding="utf-8"),
                                        encoding="utf-8")
    return store, "cp-003"


def _golden():
    return (FIXTURES / "old_format_brief.golden.md").read_text(encoding="utf-8")


def test_old_fixture_has_no_new_keys():
    d = json.loads((FIXTURES / "old_format_cp.json").read_text(encoding="utf-8"))
    assert all(set(x) == {"decision", "reason"} for x in d["decisions"]) and "workspace" not in d


def test_old_fixture_brief_byte_identical_via_store(tmp_path):
    store, ref = _install_old_fixture(tmp_path / "h")
    cp = store.get(ref)
    assert cp.checkpoint_id == "cp-003"
    assert render_brief(cp).encode("utf-8") == _golden().encode("utf-8")


def test_old_fixture_brief_byte_identical_via_mcp_resume(tmp_path):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server

    store, ref = _install_old_fixture(tmp_path / "h")
    out = asyncio.run(create_server(store).call_tool("resume_checkpoint", {"ref": ref}))
    text = out[0][0].text if isinstance(out, tuple) else (
        out.content[0].text if hasattr(out, "content") else out[0].text)
    assert text == _golden()


def test_old_fixture_brief_byte_identical_via_cli(tmp_path):
    home = tmp_path / "h"
    _install_old_fixture(home)
    env = {**os.environ, "AI_CHECKPOINT_HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_NOSYSTEM": "1"}
    r = subprocess.run([sys.executable, "-m", "ai_checkpoint", "resume", "cp-003"],
                       capture_output=True, env=env)
    assert r.returncode == 0
    assert r.stdout.decode("utf-8") == _golden()
