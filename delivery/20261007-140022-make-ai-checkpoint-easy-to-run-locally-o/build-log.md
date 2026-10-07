
## F-001 attempt 1
- What changed: src/ai_checkpoint/server.py (SERVER_INSTRUCTIONS expanded: routing, bare-ref resume, naming, confirm step, list_checkpoints; already passed to both MCPServer and FastMCP fallback via `_Server(..., instructions=)`); tests/test_server.py (new initialize-instructions test, also checks save description equals SAVE_DESCRIPTION)
- How to run it: python -m ai_checkpoint.server
- Tests: `python -m pytest -q`
- User-visible changes: the `instructions` string returned at MCP initialize is longer and more directive.
- Notes: schema.py untouched.
