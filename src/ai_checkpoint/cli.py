"""Thin CLI over the same store: save, list, get, resume. Stdlib only."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .brief import estimate_tokens, render_brief
from .errors import CheckpointError
from .store import GitStore


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai-checkpoint", description="Named restore points for AI chats.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="save a checkpoint from a JSON file")
    s.add_argument("--file", required=True, help="checkpoint JSON file ('-' for stdin)")
    ls = sub.add_parser("list", help="list checkpoints, newest first")
    ls.add_argument("--chat", metavar="NAME", help="only this chat")
    g = sub.add_parser("get", help="print a stored checkpoint as JSON")
    g.add_argument("ref")
    r = sub.add_parser("resume", help="print the resume brief")
    r.add_argument("ref")
    return p


def _run(args) -> int:
    store = GitStore()
    if args.cmd == "save":
        try:
            raw = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
            data = json.loads(raw)
        except (OSError, UnicodeDecodeError) as e:
            raise CheckpointError(f"cannot read {args.file}: {e}")
        except json.JSONDecodeError as e:
            raise CheckpointError(f"{args.file} is not valid JSON: {e}")
        except RecursionError:
            raise CheckpointError(f"{args.file} is nested too deeply")
        if not isinstance(data, dict):
            raise CheckpointError(
                f"{'stdin' if args.file == '-' else args.file} must contain a JSON object (got {type(data).__name__})")
        print(json.dumps(store.save(data).to_dict(), indent=2))
    elif args.cmd == "list":
        listing = store.list(args.chat)
        if not listing.checkpoints:
            print("no checkpoints")
        for chat, entries in listing.chats.items():
            print(chat)
            for e in entries:
                src = f"  <- {e.resumed_from}" if e.resumed_from else ""
                print(f"  {e.checkpoint_id}  {e.checkpoint_name}  {e.created_at}  "
                      f"~{e.brief_tokens} tokens{src}")
    elif args.cmd == "get":
        cp = store.get(args.ref)
        brief = render_brief(cp)
        print(json.dumps({**cp.to_dict(), "brief_chars": len(brief),
                          "brief_tokens": estimate_tokens(brief)}, indent=2, ensure_ascii=False))
    elif args.cmd == "resume":
        sys.stdout.write(render_brief(store.get(args.ref)))
    return 0


def _force_utf8() -> None:
    """Emit UTF-8 whatever the console code page is (e.g. cp1252 on Windows).

    Output only: stdin is deliberately left alone so input decoding is unchanged.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            if (getattr(stream, "encoding", None) or "").lower().replace("_", "-") in ("utf-8", "utf8"):
                continue  # already UTF-8: leave the stream (and its error handler) untouched
            try:
                # keep each stream's existing error handler (e.g. stderr's backslashreplace)
                reconfigure(encoding="utf-8", errors=stream.errors)
            except (OSError, ValueError):
                pass


def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8()
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except CheckpointError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (RecursionError, ValueError, TypeError, KeyError) as e:  # unexpected-but-parseable input
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
