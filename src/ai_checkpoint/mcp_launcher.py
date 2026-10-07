"""Entry point for ``ai-checkpoint-mcp``: explains a missing ``mcp`` extra instead of a traceback."""
from __future__ import annotations

import sys

MISSING_MCP_MESSAGE = (
    "ai-checkpoint-mcp needs the 'mcp' extra, which is not installed. "
    "Install it as 'ai-checkpoint[mcp]', for example: "
    'uvx --from "ai-checkpoint[mcp] @ git+https://github.com/<owner>/ai-checkpoint" ai-checkpoint-mcp'
)


def main() -> None:
    try:
        from .server import main as server_main
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] in {"mcp", "pydantic"}:
            print(MISSING_MCP_MESSAGE, file=sys.stderr)
            raise SystemExit(1)
        raise
    server_main()


if __name__ == "__main__":
    main()
