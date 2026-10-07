# Dogfooding log

Real resumes of real chats, and what the resumed chat got right or wrong.

## 2026-10-07: `ai-checkpoint/after-local-setup` (cp-003)
- Saved from the long build chat (research → idea → two consultancy runs → local setup). Resumed in a fresh Claude cloud session through the Mac's MCP server.
- **Result: worked.** The resumed chat stated the right current step and next steps, and answered a follow-up ("why did we drop hooks?") correctly from the decisions and reasons.
- **Gap 1:** it could explain *why* hooks were dropped but not whether they were ever prototyped. Decisions carry the reason but not how far the alternative got.
- **Gap 2:** the working environment wasn't carried over. The resumed chat had to request access to `~/projects/ai-checkpoint` again before editing docs. That led to ROADMAP item 8.

## 2026-10-07: first real eval run (paused)
- delivery-restructure on `google/gemini-3.8-flash-20260902` via OpenRouter: checkpoint 100% recall / 0 contradictions / 2148 tokens; summary 95% / 0 / 1080; full history 97% / 0 / 2697. The summary lost a decision's reason ("gives up the cheap local routes").
- invoice-sync result was overwritten (both runs used the same `--out`). A Qwen run hung for about an hour with no output.
- Eval paused by Chirag. To fix later: per-call timeout, a progress line per call, separate output folder per scenario, long (100+ message) scenarios.
