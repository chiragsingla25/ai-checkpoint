"""F-002: workspace section and the 'Set up first' checklist."""
import asyncio
import copy

import pytest
from disk import cp_path, disk_text, remove_cp, tree_bytes

from ai_checkpoint import GitStore
from ai_checkpoint.brief import render_brief
from ai_checkpoint.errors import ValidationError
from ai_checkpoint.model import Checkpoint

FULL = {
    "files": [{"path": "src/a.py", "note": "start here", "status": "still_relevant"}],
    "repos": [{"path": "~/proj", "branch": "main", "last_commit": "abc1234 fix", "status": "still_relevant"}],
    "access": [{"path": "~/proj", "permissions": ["push", "delete"], "status": "still_relevant"}],
    "connectors": [{"name": "GitHub", "note": "read PRs", "status": "done_with"}],
    "tools": [{"name": "venv ~/aic-venv", "status": "still_relevant"}],
    "env_vars": [{"name": "ANTHROPIC_API_KEY", "status": "still_relevant"}],
    "skills": [{"name": "consultancy:deliver", "status": "done_with"}],
    "references": [{"name": "ticket", "url": "https://example.com/t/1", "note": "spec", "status": "still_relevant"}],
}


def _ws(valid, ws):
    valid["workspace"] = ws
    return valid


def test_full_workspace_roundtrips(valid):
    cp = Checkpoint.from_dict(_ws(valid, copy.deepcopy(FULL)))
    assert cp.to_dict()["workspace"] == FULL
    assert Checkpoint.from_dict(cp.to_dict()).to_dict() == cp.to_dict()


@pytest.mark.parametrize("variant", ["absent", None, {}, {"repos": None}])
def test_missing_null_or_empty_workspace_defaults(valid, variant):
    if variant != "absent":
        valid["workspace"] = variant
    cp = Checkpoint.from_dict(valid)
    assert all(v == [] for v in cp.workspace.values())
    assert "workspace" not in cp.to_dict()


def test_partial_workspace(valid):
    cp = Checkpoint.from_dict(_ws(valid, {"repos": FULL["repos"]}))
    assert cp.workspace["files"] == [] and len(cp.workspace["repos"]) == 1
    assert list(cp.to_dict()["workspace"]) == ["repos"]


@pytest.mark.parametrize(
    "ws,field",
    [
        ({"repos": [{"path": "p", "status": "maybe"}]}, "workspace.repos[0].status"),
        ({"repos": [{"path": "p"}]}, "workspace.repos[0].status"),
        ({"repos": [{"status": "done_with"}]}, "workspace.repos[0].path"),
        ({"repos": [{"path": " ", "status": "done_with"}]}, "workspace.repos[0].path"),
        ({"tools": [{"status": "done_with"}]}, "workspace.tools[0].name"),
        ({"files": [{"path": "a", "status": "done_with"}, {"status": "done_with"}]}, "workspace.files[1].path"),
        ({"access": [{"path": "a", "permissions": "push", "status": "done_with"}]}, "workspace.access[0].permissions"),
        ({"repos": "x"}, "workspace.repos"),
        ({"repos": ["x"]}, "workspace.repos[0]"),
        ("x", "workspace"),
        ({"env_vars": [{"name": "=abc", "status": "done_with"}]}, "workspace.env_vars[0].name"),
    ],
)
def test_invalid_workspace_names_field(valid, ws, field):
    with pytest.raises(ValidationError) as e:
        Checkpoint.from_dict(_ws(valid, ws))
    assert e.value.field == field


def test_env_var_value_never_stored(valid, tmp_path):
    ws = {"env_vars": [{"name": "ANTHROPIC_API_KEY=sk-ant-abc123def456ghi789", "status": "still_relevant"},
                       {"name": "FOO=bar-baz-12345", "status": "still_relevant"}]}
    cp = Checkpoint.from_dict(_ws(valid, ws))
    assert [i["name"] for i in cp.workspace["env_vars"]] == ["ANTHROPIC_API_KEY", "FOO"]
    store = GitStore(tmp_path / "h")
    res = store.save(_ws(copy.deepcopy(valid), ws))
    raw = disk_text(store, res.checkpoint_id)
    assert "sk-ant" not in raw and "abc123" not in raw and "bar-baz" not in raw
    assert "ANTHROPIC_API_KEY" in raw and "=" not in raw.split('"env_vars"')[1].split("]")[0]


def test_secrets_in_workspace_strings_redacted_on_disk(valid, tmp_path):
    ws = {
        "references": [{"name": "doc", "url": "https://x.example/api?token=abcd1234efgh", "status": "still_relevant"}],
        "tools": [{"name": "curl", "note": "uses Bearer abcdef1234567890xyz", "status": "still_relevant"}],
        "connectors": [{"name": "db", "note": "password=hunter2hunter2", "status": "still_relevant"}],
        "files": [{"path": "a.py", "note": "key sk-ant-abc123def456ghi789", "status": "still_relevant"}],
    }
    store = GitStore(tmp_path / "h")
    res = store.save(_ws(valid, ws))
    raw = disk_text(store, res.checkpoint_id)
    for leak in ("abcd1234efgh", "abcdef1234567890xyz", "hunter2hunter2", "sk-ant-abc123"):
        assert leak not in raw
    assert "[REDACTED]" in raw


def test_brief_checklist_lists_only_still_relevant(valid):
    out = render_brief(Checkpoint.from_dict(_ws(valid, copy.deepcopy(FULL))))
    i = out.index("## Set up first")
    assert out.index("## Notes from the previous AI") < i < out.index("## Before you continue")
    block = out[i : out.index("## Before you continue")]
    for want in ("~/proj", "push, delete", "main", "abc1234 fix", "venv ~/aic-venv",
                 "ANTHROPIC_API_KEY", "src/a.py", "https://example.com/t/1"):
        assert want in block
    assert "GitHub" not in block and "consultancy:deliver" not in block  # done_with
    assert "Connectors to check" not in block and "Skills, plugins" not in block


def test_brief_tells_ai_to_ask_before_access(valid):
    out = render_brief(Checkpoint.from_dict(_ws(valid, copy.deepcopy(FULL))))
    assert "Ask the user before you request any folder access or connector" in out
    assert "do not assume" in out


def test_no_checklist_without_workspace_or_when_all_done(valid):
    assert "Set up first" not in render_brief(Checkpoint.from_dict(valid))
    done = {c: [dict(i, status="done_with") for i in items] for c, items in FULL.items()}
    assert "Set up first" not in render_brief(Checkpoint.from_dict(_ws(valid, done)))
    assert render_brief(Checkpoint.from_dict(_ws(copy.deepcopy(valid), done))) == render_brief(
        Checkpoint.from_dict(copy.deepcopy(VALID_NO_WS(valid)))
    )


def VALID_NO_WS(valid):
    d = copy.deepcopy(valid)
    d.pop("workspace", None)
    return d


def test_save_description_asks_for_workspace():
    from ai_checkpoint.schema import SAVE_DESCRIPTION as D

    for word in ("`workspace`", "still_relevant", "done_with", "NAMES", "never their values"):
        assert word in D


def test_mcp_tool_schema_and_roundtrip(tmp_path, valid):
    pytest.importorskip("mcp")
    from ai_checkpoint.server import create_server

    root = tmp_path / "h"
    server = create_server(GitStore(root))
    tools = asyncio.run(server.list_tools())
    t = [x for x in tools if x.name == "save_checkpoint"][0]
    schema = getattr(t, "inputSchema", None) or t.input_schema
    assert "workspace" in schema["properties"]
    assert "still_relevant" in str(schema) and "done_with" in str(schema)
    args = {k: v for k, v in valid.items() if k != "client"}
    args["workspace"] = {"repos": [{"path": "p", "branch": "main", "status": "still_relevant"}]}
    asyncio.run(server.call_tool("save_checkpoint", args))
    got = GitStore(root).get("cp-001").to_dict()["workspace"]
    assert got == {"repos": [{"path": "p", "branch": "main", "status": "still_relevant"}]}


URL_CASES = [
    ("https://user:tok_abcdef123456@git.example.com/r.git", "tok_abcdef123456", "https://user:[REDACTED]@git.example.com/r.git"),
    ("https://oauth2:glpat-abcdefghij1234567890@gitlab.com/x", "glpat-abcdefghij1234567890", "https://oauth2:[REDACTED]@gitlab.com/x"),
    ("https://user:MyPassw0rd@host/x", "MyPassw0rd", "https://user:[REDACTED]@host/x"),
    ("postgres://u:hunter2pw@h/db", "hunter2pw", "postgres://u:[REDACTED]@h/db"),
]


@pytest.mark.parametrize("url,leak,want", URL_CASES)
def test_url_credentials_redacted(url, leak, want):
    from ai_checkpoint.redact import redact_text

    out = redact_text(f"clone {url} now")
    assert leak not in out
    assert want in out
    assert redact_text(out) == out  # idempotent


@pytest.mark.parametrize("url", [
    "https://example.com/t/1", "git@github.com:o/r.git", "http://localhost:8080/a",
    "https://host:8080/x@y", "https://user@host/x", "postgres://u:${DB_PASS}@h/db",
])
def test_urls_without_credentials_unchanged(url):
    from ai_checkpoint.redact import redact_text

    assert redact_text(url) == url


def test_url_credentials_in_workspace_redacted_on_disk(valid, tmp_path):
    ws = {
        "repos": [{"path": "https://user:tok_abcdef123456@git.example.com/r.git", "status": "still_relevant"}],
        "references": [{"name": "db", "url": "postgres://u:hunter2pw@h/db", "status": "still_relevant"}],
    }
    store = GitStore(tmp_path / "h")
    res = store.save(_ws(valid, ws))
    raw = disk_text(store, res.checkpoint_id)
    assert "tok_abcdef123456" not in raw and "hunter2pw" not in raw
    assert "git.example.com/r.git" in raw and "@h/db" in raw
