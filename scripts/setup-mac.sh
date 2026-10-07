#!/usr/bin/env bash
# One-command local setup for AI Checkpoint on macOS.
#
#   ./scripts/setup-mac.sh [--dry-run] [--desktop-config PATH] [--help]
#
# Builds <repo>/.venv, installs this repo with the MCP extra, registers the
# server with Claude Code (user scope) and Claude Desktop, prints next steps.
# Written for macOS's stock bash 3.2 and BSD userland.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/setup-mac.sh [options]

Sets up AI Checkpoint locally:
  1. creates (or reuses) a virtualenv at <repo>/.venv and installs ".[mcp]"
  2. registers the MCP server "ai-checkpoint" with Claude Code (user scope),
     if the `claude` CLI is on PATH
  3. adds/updates the "ai-checkpoint" entry in the Claude Desktop config
     (a backup of the old file is written next to it first)

Options:
  --dry-run               print what would be done; change nothing
  --desktop-config PATH   Claude Desktop config file to edit
                          (default: ~/Library/Application Support/Claude/claude_desktop_config.json)
  -h, --help              show this help

Environment:
  PYTHON                  interpreter used to create the venv (default: python3); needs 3.10+

Checkpoints are stored in $HOME/.ai-checkpoint.
EOF
}

DRY_RUN=0
DESKTOP_CONFIG=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --desktop-config)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "error: --desktop-config needs a PATH" >&2; exit 2
      fi
      DESKTOP_CONFIG="$2"; shift 2 ;;
    --desktop-config=*)
      DESKTOP_CONFIG="${1#--desktop-config=}"
      if [ -z "$DESKTOP_CONFIG" ]; then
        echo "error: --desktop-config needs a PATH" >&2; exit 2
      fi
      shift ;;
    *) echo "error: unknown option: $1" >&2; echo >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "${HOME:-}" ]; then
  echo "error: HOME is not set" >&2; exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
VENV="$REPO_ROOT/.venv"
SERVER_BIN="$VENV/bin/ai-checkpoint-mcp"
STORE_HOME="$HOME/.ai-checkpoint"
SERVER_NAME="ai-checkpoint"
PY="${PYTHON:-python3}"
if [ -z "$DESKTOP_CONFIG" ]; then
  DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
fi

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
# Run a command, or only show it under --dry-run.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    say "[dry-run] would run: $*"
  else
    "$@"
  fi
}

# ---- 1. Python check (before anything is created) --------------------------
command -v "$PY" >/dev/null 2>&1 || die "Python not found: $PY (set PYTHON=/path/to/python3.10+)"
PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
case "$PYVER" in
  [0-9]*.[0-9]*) ;;
  *)
    PYVER="$("$PY" --version 2>&1 | sed -n 's/^Python \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n 1)"
    ;;
esac
case "$PYVER" in
  [0-9]*.[0-9]*) ;;
  *) die "could not determine the version of $PY; AI Checkpoint needs Python 3.10 or newer" ;;
esac
PYMAJOR="${PYVER%%.*}"
PYMINOR="${PYVER#*.}"
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 10 ]; }; then
  die "AI Checkpoint needs Python 3.10 or newer; $PY is $PYVER. Install a newer Python (e.g. 'brew install python') or set PYTHON=/path/to/python3.10+"
fi
say "Using $PY (Python $PYVER)"

# ---- Desktop config helper (Python stdlib; no jq) ---------------------------
# modes: check  - validate the existing file only
#        apply  - add/replace mcpServers.ai-checkpoint (backup first)
#        plan   - like apply, but only report
desktop_config() {
  "$PY" - "$1" "$DESKTOP_CONFIG" "$SERVER_NAME" "$SERVER_BIN" "$STORE_HOME" <<'PYEOF'
import json, os, shutil, sys, tempfile, time

mode, path, name, command, store = sys.argv[1:6]

def fail(msg):
    sys.stderr.write("error: %s\n" % msg)
    sys.exit(1)

existing = None
if os.path.exists(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (OSError, UnicodeDecodeError) as e:
        fail("cannot read Claude Desktop config %s: %s" % (path, e))
    if raw.strip():
        try:
            existing = json.loads(raw)
        except ValueError as e:
            fail("Claude Desktop config %s is not valid JSON (%s); fix or move it and re-run. The file was left untouched." % (path, e))
        if not isinstance(existing, dict):
            fail("Claude Desktop config %s must be a JSON object; left untouched." % path)
    else:
        existing = {}
    if "mcpServers" in existing and not isinstance(existing["mcpServers"], dict):
        fail("'mcpServers' in %s is not an object; left untouched." % path)

if mode == "check":
    sys.exit(0)

entry = {"command": command, "env": {"AI_CHECKPOINT_HOME": store}}
new = json.loads(json.dumps(existing)) if existing is not None else {}
new.setdefault("mcpServers", {})[name] = entry

if existing is not None and new == existing:
    print("Claude Desktop config already up to date: %s" % path)
    sys.exit(0)

if mode == "plan":
    if existing is None:
        print("[dry-run] would create %s with mcpServers.%s -> %s" % (path, name, command))
    else:
        print("[dry-run] would back up %s and set mcpServers.%s -> %s" % (path, name, command))
    sys.exit(0)

parent = os.path.dirname(os.path.abspath(path))
try:
    os.makedirs(parent, exist_ok=True)
    if existing is not None:
        backup = "%s.bak-%s" % (path, time.strftime("%Y%m%d%H%M%S"))
        n = 0
        while os.path.exists(backup):
            n += 1
            backup = "%s.bak-%s-%d" % (path, time.strftime("%Y%m%d%H%M%S"), n)
        shutil.copy2(path, backup)
        print("Backed up existing config to %s" % backup)
    fd, tmp = tempfile.mkstemp(prefix=".claude_desktop_config.", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(new, f, indent=2)
            f.write("\n")
        if existing is not None:
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
except OSError as e:
    fail("could not write %s: %s" % (path, e))
print("Updated Claude Desktop config: %s" % path)
PYEOF
}

# Validate the Desktop config up front so a bad file stops us before any change.
desktop_config check

# ---- 2. Virtualenv + install -----------------------------------------------
if [ -x "$VENV/bin/python" ]; then
  say "Reusing virtualenv $VENV"
else
  say "Creating virtualenv $VENV"
  run "$PY" -m venv "$VENV"
fi
say "Installing AI Checkpoint with the MCP extra"
run "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -e "$REPO_ROOT[mcp]"
if [ "$DRY_RUN" -eq 0 ]; then
  [ -x "$SERVER_BIN" ] || die "install finished but $SERVER_BIN was not created"
  "$VENV/bin/python" -c 'import mcp, ai_checkpoint' || die "installed environment cannot import mcp and ai_checkpoint"
  mkdir -p "$STORE_HOME"
fi

# ---- 3. Claude Code ---------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then
    say "[dry-run] would run: claude mcp remove $SERVER_NAME -s local   (failure ignored)"
    say "[dry-run] would run: claude mcp remove $SERVER_NAME -s user   (failure ignored)"
    say "[dry-run] would run: claude mcp add -s user $SERVER_NAME -e AI_CHECKPOINT_HOME=$STORE_HOME -- $SERVER_BIN"
  else
    say "Registering with Claude Code (user scope)"
    claude mcp remove "$SERVER_NAME" -s local >/dev/null 2>&1 || true
    claude mcp remove "$SERVER_NAME" -s user >/dev/null 2>&1 || true
    claude mcp add -s user "$SERVER_NAME" -e "AI_CHECKPOINT_HOME=$STORE_HOME" -- "$SERVER_BIN" \
      || die "'claude mcp add' failed"
  fi
else
  say "Claude Code registration skipped: the 'claude' CLI is not on PATH."
  say "  Later, run: claude mcp add -s user $SERVER_NAME -e AI_CHECKPOINT_HOME=$STORE_HOME -- $SERVER_BIN"
fi

# ---- 4. Claude Desktop ------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  desktop_config plan
else
  desktop_config apply
fi

# ---- 5. Next steps ----------------------------------------------------------
say
if [ "$DRY_RUN" -eq 1 ]; then
  say "Dry run complete; nothing was changed."
  exit 0
fi
cat <<EOF
Done. Next steps:
  1. Restart Claude Desktop (quit and reopen) so it loads the new server.
  2. In Claude Code, run /mcp and check that "$SERVER_NAME" is connected.
  3. Try it: in a chat say "checkpoint this chat as trial/test-v1", then open a
     new chat and say "resume trial/test-v1".
Checkpoints are stored in $STORE_HOME
EOF
