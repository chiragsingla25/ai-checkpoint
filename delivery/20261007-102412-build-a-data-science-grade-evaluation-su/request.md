# Request

Build a data-science grade evaluation suite and dataset for AI Checkpoint handovers (lean version + workspace capture/restore; no drift test). Everything must run offline with the existing FakeModel for tests/QA, and for real with --model openai via OpenRouter (OPENAI_BASE_URL) on Chirag's Mac.

(1) Harden the eval runner: per-call timeout and bounded retries, a progress line per model call, a separate output folder per scenario/run (no overwriting), optional parallel calls, and resuming a partially finished run from cached call results.

(2) Dataset: a deterministic, seeded scenario generator (no model needed) that writes scenario JSON files with answer keys, plus the generated dataset committed under examples/ or a datasets/ folder: 2 task types (coding and data analysis) x 3 lengths (about 20, 50, 100 messages). Each scenario plants: decisions with reasons and rejected alternatives; exact numbers/commands/code that must be reproduced verbatim; a value corrected mid-way (the old value is a stale trap); a known next step; and an environment manifest (files/folders, repo with branch and last commit, folder access granted, connectors/MCP servers, tools, env var NAMES, skills, references), each item labelled still_relevant or done_with, with traps: a folder used early then abandoned, a file renamed mid-way, and an env var whose secret-looking value appears in the chat. Filler turns must be varied and realistic enough that facts are not trivially at fixed positions.

(3) Handovers and metrics: variants checkpoint, plain summary, full history, last-20-messages, and no-handover. Metrics: key-fact recall, contradictions, stale-fact use, verbatim exact match (scored by code, no judge), next-step accuracy, brief tokens, recall per 1k tokens; N repeats per cell (default 3) with bootstrap 95% confidence intervals.

(4) Workspace stage 1 (capture, scored by code): from the saved checkpoint's workspace section compute capture recall, capture precision, status accuracy (still_relevant vs done_with) and secret leakage (must be 0), against the manifest.

(5) Workspace stage 2 (restore): the resumed model runs a few turns against a mock environment with fake tools (request_folder_access, check_connector, open_file, ask_user, start_work) through tool calling; log tool calls and score setup recall, setup precision, ask-before-access compliance, re-asked questions (asking the user something already answered), turns to ready, and first-action correctness, for checkpoint, summary and full-history handovers. FakeModel must support a scripted tool-calling mode so this is testable offline.

(6) A report command that aggregates results across scenarios into a markdown report with tables and PNG charts (recall vs conversation length per variant; loss by category; capture/restore metrics; cost/quality trade-off).

Keep the existing two example scenarios and existing CLI behaviour working. Ask before expanding scope.

## Scope change (Chirag, at the approval gate)
Build the LEAN version only. The product (save/resume/MCP server) must not change; only the eval kit and dataset.
1. Dataset: seeded generator (no model) + committed datasets/handover-v1 with 6 scenarios: coding and data_analysis x 20/50/100 messages, with answer_key (decisions + reasons + rejected alternatives, verbatim code/numbers/commands, a corrected value as stale trap, next step) and environment manifest with traps (abandoned folder, renamed file, fake secret value) — as in the original request.
2. Minimal runner fixes: per-call timeout with 1 retry, a `suite` command writing one folder per scenario, and refusing to overwrite an existing results.json (unless --force).
3. Batched questions to save tokens: per handover variant ONE call answers all probes, and ONE judge call grades all answers. Target about 8 model calls per scenario (compaction, summary, 3 answer calls, 3 judge calls).
4. Extra scores computed by code (no judge): verbatim exact match, stale-fact use, next-step accuracy, brief tokens; plus workspace capture scoring from the checkpoint's workspace section (capture recall, precision, status accuracy, secret leakage).
Keep the current 3 handovers (checkpoint, summary, full_history).
OUT OF SCOPE for now: last-20 and no-handover variants, repeats and bootstrap CIs, parallel workers, resume-from-cache, the restore stage with mock tools, the report command and charts. Real runs will use a Qwen model via OpenRouter (OPENAI_BASE_URL); budget about 50 calls / 0.25M input tokens for the whole dataset.
