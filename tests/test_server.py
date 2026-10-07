import asyncio
import os
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from ai_checkpoint import GitStore  # noqa: E402
from ai_checkpoint.server import create_server  # noqa: E402

TOOLS = {"save_checkpoint", "list_checkpoints", "get_checkpoint", "resume_checkpoint"}


def _text(result):
    return "".join(getattr(c, "text", "") for c in result.content)


def _is_error(result):
    return getattr(result, "is_error", None) if hasattr(result, "is_error") else result.isError


def _params(home):
    env = {**os.environ, "AI_CHECKPOINT_HOME": str(home), "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_NOSYSTEM": "1"}
    return StdioServerParameters(command=sys.executable, args=["-m", "ai_checkpoint.server"], env=env)


def _run_stdio(home, fn):
    async def go():
        async with stdio_client(_params(home)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await fn(s)
    return asyncio.run(asyncio.wait_for(go(), 60))


def test_stdio_session_end_to_end(tmp_path, valid):
    async def scenario(s):
        out = {}
        out["tools"] = await s.list_tools()
        out["prompts"] = await s.list_prompts()
        saved = await s.call_tool("save_checkpoint", valid)
        out["saved"] = saved
        out["list"] = await s.call_tool("list_checkpoints", {})
        out["get"] = await s.call_tool("get_checkpoint", {"ref": "forecasting/v1"})
        out["resume"] = await s.call_tool("resume_checkpoint", {"ref": "cp-001"})
        out["prompt"] = await s.get_prompt("resume", {"ref": "cp-001"})
        bad = await s.call_tool("save_checkpoint", {k: v for k, v in valid.items() if k != "objective"})
        out["bad"] = bad
        out["after"] = await s.call_tool("resume_checkpoint", {"ref": "v1"})
        return out

    out = _run_stdio(tmp_path / "h", scenario)
    assert {t.name for t in out["tools"].tools} == TOOLS
    prompts = {p.name: p for p in out["prompts"].prompts}
    assert "ref" in {a.name for a in prompts["resume"].arguments}
    assert not _is_error(out["saved"])
    assert "cp-001" in _text(out["saved"])
    assert len(out["saved"].structuredContent["commit"]) >= 7 if hasattr(out["saved"], "structuredContent") else True
    assert "forecasting" in _text(out["list"]) and "brief_tokens" in _text(out["list"])
    assert "brief_tokens" in _text(out["get"]) and "Prophet" in _text(out["get"])
    brief = _text(out["resume"])
    assert brief.startswith("You are continuing work from checkpoint cp-001")
    assert out["prompt"].messages[0].content.text == brief
    assert _is_error(out["bad"]) and "objective" in _text(out["bad"])
    assert _text(out["after"]) == brief  # server still running, deterministic


def test_save_schema_documents_sections(tmp_path):
    async def scenario(s):
        return await s.list_tools()

    tools = {t.name: t for t in _run_stdio(tmp_path / "h", scenario).tools}
    schema = getattr(tools["save_checkpoint"], "inputSchema", None) or tools["save_checkpoint"].input_schema
    props = schema["properties"]
    for name in ("chat_name", "checkpoint_name", "objective", "context", "decisions", "completed",
                 "current_step", "next_steps", "open_questions", "verbatim", "last_exchange",
                 "notes_for_next_ai", "client", "resumed_from"):
        assert props[name].get("description"), name
    assert {"objective", "current_step", "next_steps"} <= set(schema["required"])
    assert "client" not in schema["required"] and "resumed_from" not in schema["required"]
    desc = tools["save_checkpoint"].description
    for phrase in ("EVERY section", "word for word", "Never invent", "verbatim"):
        assert phrase in desc


def _call(server, name, args):
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        return asyncio.run(server.call_tool(name, args))
    except ToolError as e:
        return e


def test_in_process_errors_and_recovery(root, valid):
    server = create_server(GitStore(root))
    ok = _call(server, "save_checkpoint", valid)
    assert not isinstance(ok, Exception)

    missing = {k: v for k, v in valid.items() if k != "current_step"}
    assert "current_step" in str(_call(server, "save_checkpoint", missing))
    assert "next_steps" in str(_call(server, "save_checkpoint", {**valid, "next_steps": []}))
    assert "nope" in str(_call(server, "get_checkpoint", {"ref": "nope"}))
    assert "resumed_from" in str(_call(server, "save_checkpoint", {**valid, "resumed_from": "cp-099"}))
    again = _call(server, "save_checkpoint", {**valid, "checkpoint_name": "v2", "resumed_from": "cp-001"})
    assert not isinstance(again, Exception)
    assert GitStore(root).get("v2").resumed_from == "cp-001"


def test_initialize_instructions_route_to_tools(tmp_path):
    async def go():
        async with stdio_client(_params(tmp_path / "h")) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = await s.list_tools()
                return init, tools

    init, tools = asyncio.run(asyncio.wait_for(go(), 60))
    text = init.instructions
    assert isinstance(text, str) and text.strip()
    for needle in ("save_checkpoint", "resume_checkpoint", "list_checkpoints", "trial/test-v1",
                   "chat_name", "checkpoint_name", "forecasting-v2", "no '/'", "split",
                   "confirm the current step", "brief", "Do not search"):
        assert needle in text, needle
    from ai_checkpoint.schema import SAVE_DESCRIPTION
    save = next(t for t in tools.tools if t.name == "save_checkpoint")
    assert save.description == SAVE_DESCRIPTION
