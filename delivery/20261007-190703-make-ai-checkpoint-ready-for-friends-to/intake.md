# Intake

## Understanding
Make AI Checkpoint installable and usable by friends on their own Mac and Windows machines straight from a public GitHub repo via `uvx --from "ai-checkpoint[mcp] @ git+<url>" ai-checkpoint-mcp`. Two parts: (1) remove the POSIX-only assumptions so save/list/get/resume, the CLI and the MCP server work on Windows with a real msvcrt save lock, and Mac/Linux unchanged; (2) prove the uvx-from-git install works and document it in a README "For testers" section.

Class of the Windows problem: platform-dependent behaviour in the store and its I/O boundaries. Edges checked in the code: the save lock (fcntl today, silent no-op elsewhere, so Windows saves are unserialised rather than broken); file encoding and line endings (writes already use utf-8 + newline="\n", reads use utf-8; CRLF can still appear if git autocrlf rewrites files, and should still parse); git subprocess output decoding (already utf-8, but no errors= handling) and user git config such as core.autocrlf/safecrlf; path construction (pathlib throughout; '/' is used only in git pathspecs and chat/name refs, which are not filesystem paths); console encoding for CLI output (non-ASCII JSON/brief printed to a cp1252 console can raise UnicodeEncodeError); git missing from PATH. File permissions: the store does not chmod anything, so nothing to port.

## Size
medium: two features touching the store, CLI, packaging and README, with a real install-from-git check, but no new product behaviour.

## Existing project
Python >=3.10 package `ai-checkpoint` (setuptools, src layout) at /home/claude/ai-checkpoint: src/ai_checkpoint/{store.py (git-backed store, `_lock` with fcntl), server.py (MCP via `mcp` SDK, optional extra), cli.py, schema.py (SAVE_DESCRIPTION, pinned by tests/test_server.py), brief.py, model.py, redact.py, eval/}. Entry points: ai-checkpoint, ai-checkpoint-mcp, checkpoint-eval. Tests: `python -m pytest -q` from the project root, currently 117 passing (~45 s). README has Quick start (macOS, scripts/setup-mac.sh), Install, MCP server, CLI, brief and eval sections. uv/uvx are installed at /root/.local/bin.

## Recommended stages
build, qa. Build the msvcrt lock, encoding/CLI hardening, friendly missing-mcp message, Windows-simulation tests and README section; QA runs the test suite and the uvx git+file stdio check.

## Assumptions
- No Windows machine is available. Windows criteria are verified by code inspection plus tests that simulate Windows on Linux (fcntl hidden, msvcrt faked, CRLF files, autocrlf git config, cp1252 stdout). Real-Windows verification is left to the testers and should be said so in the README/QA notes.
- The uvx check uses `git+file://` against a clone of committed HEAD, because the GitHub repo does not exist yet and uv installs only committed content from a git URL. Build must therefore commit before QA runs that check.
- The msvcrt lock locks a fixed 1-byte (or small) region at offset 0 of `.git/ai-checkpoint.lock`, blocking/retrying until acquired; the no-op fallback stays only for platforms with neither module.
- The documented tester command uses the `[mcp]` extra in a `git+https://github.com/<owner>/ai-checkpoint` spec; the Claude Code example uses `-s user`.
- Without the mcp extra, `ai-checkpoint-mcp` should fail with a clear hint rather than a traceback (testers will likely mistype the spec).
- Existing macOS Quick start / setup script stays as-is; the "For testers" section is added, not a replacement.
- SAVE_DESCRIPTION in schema.py must remain byte-identical.

## Open questions
