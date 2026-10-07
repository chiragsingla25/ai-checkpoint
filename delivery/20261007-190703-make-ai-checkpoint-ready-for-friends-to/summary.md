# Run summary: 20261007-190703-make-ai-checkpoint-ready-for-friends-to

Request: make AI Checkpoint testable by friends on Mac and Windows, installed from a public GitHub repo via uvx. Plan: intake -> build -> qa.

| Feature | Attempts | Verdict | Commit |
|---|---|---|---|
| F-001 Windows support (msvcrt lock, UTF-8 I/O, LF-only JSON, autocrlf off for store git) | 3 | PASS (15/15) | 2273125 |
| F-002 uvx install from git URL + README "For testers" | 1 | PASS (11/11) | see git log |

F-001 fails: attempt 1 broke stderr error messages for non-UTF-8 filenames; attempt 2 re-encoded stdin, breaking legacy-encoded piped input. Both fixed with regression tests.
Orchestrator doc tweaks after F-002 PASS (from QA notes): `where.exe uvx` for PowerShell; Claude Desktop Settings > Developer > Edit Config route.

User-visible: Windows support; `ai-checkpoint-mcp` prints an install hint instead of a traceback when the mcp extra is missing; README For testers section.
Known gaps: never run on real Windows (simulated only); Microsoft Store build of Claude Desktop may keep config elsewhere; `<owner>`/`<contact>` placeholders must be replaced before sharing.
