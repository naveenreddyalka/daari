#!/usr/bin/env bash
# Local autodev watchdog: pull main, redeploy daari serve, run live E2E, file
# a GitHub issue on regression. Runs via launchd (see scripts/launchd/).
#
# Usage:
#   scripts/autodev-local.sh            # one watchdog cycle
#   scripts/autodev-local.sh --install  # install + load launchd agents
#   scripts/autodev-local.sh --uninstall
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO/.venv"
LOG_DIR="$HOME/.daari/autodev"
RUN_LOG="$LOG_DIR/run-$(date +%Y%m%d-%H%M%S).log"
SERVE_LABEL="com.daari.serve"
WATCH_LABEL="com.daari.autodev"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
DAEMON_URL="http://127.0.0.1:11435"
OLLAMA_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"

mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$RUN_LOG"; }

render_plist() { # $1 template path, $2 dest path
  sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" "$1" > "$2"
}

install_agents() {
  mkdir -p "$LAUNCH_AGENTS"
  render_plist "$REPO/scripts/launchd/$SERVE_LABEL.plist" "$LAUNCH_AGENTS/$SERVE_LABEL.plist"
  render_plist "$REPO/scripts/launchd/$WATCH_LABEL.plist" "$LAUNCH_AGENTS/$WATCH_LABEL.plist"
  launchctl unload "$LAUNCH_AGENTS/$SERVE_LABEL.plist" 2>/dev/null || true
  launchctl unload "$LAUNCH_AGENTS/$WATCH_LABEL.plist" 2>/dev/null || true
  launchctl load "$LAUNCH_AGENTS/$SERVE_LABEL.plist"
  launchctl load "$LAUNCH_AGENTS/$WATCH_LABEL.plist"
  echo "Installed and loaded: $SERVE_LABEL (keeps daari serve alive), $WATCH_LABEL (watchdog every 2h)."
  echo "Logs: $LOG_DIR"
}

uninstall_agents() {
  launchctl unload "$LAUNCH_AGENTS/$SERVE_LABEL.plist" 2>/dev/null || true
  launchctl unload "$LAUNCH_AGENTS/$WATCH_LABEL.plist" 2>/dev/null || true
  rm -f "$LAUNCH_AGENTS/$SERVE_LABEL.plist" "$LAUNCH_AGENTS/$WATCH_LABEL.plist"
  echo "Unloaded and removed launchd agents."
}

case "${1:-}" in
  --install) install_agents; exit 0 ;;
  --uninstall) uninstall_agents; exit 0 ;;
esac

FAILURES=()

file_regression_issue() {
  local title="$1"
  local body_file="$2"
  # Dedupe: skip when an open regression issue with the same title exists.
  local existing
  existing=$(gh issue list --repo naveenreddyalka/daari --state open --label regression \
    --search "in:title \"$title\"" --json number --jq 'length' 2>/dev/null || echo 0)
  if [ "${existing:-0}" -gt 0 ]; then
    log "Open regression issue already exists for: $title — skipping create."
    return
  fi
  gh issue create --repo naveenreddyalka/daari \
    --title "$title" \
    --label "auto-dev,regression" \
    --body-file "$body_file" >> "$RUN_LOG" 2>&1 \
    && log "Filed regression issue: $title" \
    || log "WARN: could not file issue (gh auth/network?)"
}

# --- 1. Update to latest main -------------------------------------------------
cd "$REPO"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  log "Repo on branch '$BRANCH', not main — skipping pull/deploy (dev work in progress)."
elif ! git diff --quiet || ! git diff --cached --quiet; then
  log "Uncommitted changes on main — skipping pull/deploy."
else
  BEFORE=$(git rev-parse HEAD)
  git pull --ff-only origin main >> "$RUN_LOG" 2>&1 || log "WARN: git pull failed"
  AFTER=$(git rev-parse HEAD)
  if [ "$BEFORE" != "$AFTER" ]; then
    log "Updated main: ${BEFORE:0:7} -> ${AFTER:0:7}"
    if git diff --name-only "$BEFORE" "$AFTER" | grep -q "pyproject.toml"; then
      log "pyproject.toml changed — reinstalling package"
      "$VENV/bin/pip" install -e ".[dev]" >> "$RUN_LOG" 2>&1
    fi
    log "Restarting daari serve to deploy new code"
    launchctl kickstart -k "gui/$(id -u)/$SERVE_LABEL" 2>/dev/null || true
    sleep 3
  else
    log "main already up to date (${AFTER:0:7})"
  fi
fi

# --- 2. Daemon health ---------------------------------------------------------
if ! curl -sf --max-time 5 "$DAEMON_URL/health" > /dev/null; then
  log "daari serve not responding — kickstarting"
  launchctl kickstart -k "gui/$(id -u)/$SERVE_LABEL" 2>/dev/null || true
  sleep 5
fi
if curl -sf --max-time 5 "$DAEMON_URL/health" > /dev/null; then
  log "daemon healthy at $DAEMON_URL"
else
  log "FAIL: daemon unreachable at $DAEMON_URL"
  FAILURES+=("daemon unreachable")
fi

# --- 3. Live Ollama integration tests -----------------------------------------
if curl -sf --max-time 5 "$OLLAMA_URL/api/tags" > /dev/null; then
  log "Running live integration tests"
  if OLLAMA_HOST="$OLLAMA_URL" "$VENV/bin/python" -m pytest -m integration -q >> "$RUN_LOG" 2>&1; then
    log "integration tests: PASS"
  else
    log "FAIL: live integration tests"
    FAILURES+=("live integration tests failed")
  fi
else
  log "SKIP: Ollama not reachable at $OLLAMA_URL"
fi

# --- 4. Cursor-shaped E2E smoke (18 tools + input_text, streaming) -------------
SMOKE_OUT="$LOG_DIR/smoke-latest.json"
"$VENV/bin/python" - "$DAEMON_URL" "$SMOKE_OUT" <<'PY' >> "$RUN_LOG" 2>&1
import json, sys
import httpx

daemon, out_path = sys.argv[1], sys.argv[2]
tools = [{"type": "function", "function": {"name": f"tool_{i}", "description": "ide tool",
          "parameters": {"type": "object", "properties": {}}}} for i in range(18)]
payload = {
    "model": "daari", "stream": True, "stream_options": {"include_usage": True},
    "messages": [
        {"role": "system", "content": "You are a coding assistant with tools."},
        {"role": "user", "content": [{"type": "input_text", "text": "What is 2 plus 2?"}]},
    ],
    "tools": tools,
}
r = httpx.post(f"{daemon}/v1/chat/completions", json=payload, timeout=120)
chunks = sum(1 for ln in r.text.splitlines() if '"content"' in ln and '"delta"' in ln)
result = {"status_code": r.status_code, "content_chunks": chunks}
json.dump(result, open(out_path, "w"))
print(f"smoke: {result}")
sys.exit(0 if r.status_code == 200 and chunks > 0 else 1)
PY
if [ $? -eq 0 ]; then
  log "cursor smoke: PASS ($(cat "$SMOKE_OUT" 2>/dev/null))"
else
  log "FAIL: cursor smoke ($(cat "$SMOKE_OUT" 2>/dev/null))"
  FAILURES+=("cursor-shaped E2E smoke failed")
fi

# --- 5. Report -----------------------------------------------------------------
if [ ${#FAILURES[@]} -gt 0 ]; then
  COMMIT=$(git rev-parse --short HEAD)
  TITLE="[autodev] Local E2E regression on main @ $COMMIT"
  BODY_FILE="$LOG_DIR/issue-body.md"
  {
    echo "Local watchdog detected failures on \`main\` @ \`$COMMIT\` ($(date '+%Y-%m-%d %H:%M %Z'))."
    echo
    echo "## Failures"
    for f in "${FAILURES[@]}"; do echo "- $f"; done
    echo
    echo "## Log tail"
    echo '```'
    tail -60 "$RUN_LOG"
    echo '```'
    echo
    echo "Machine: $(hostname). Full log: \`$RUN_LOG\`."
  } > "$BODY_FILE"
  file_regression_issue "$TITLE" "$BODY_FILE"
  log "cycle result: FAIL (${#FAILURES[@]} failure(s))"
  exit 1
fi

log "cycle result: PASS"
# Keep last 50 run logs
ls -t "$LOG_DIR"/run-*.log 2>/dev/null | tail -n +51 | xargs rm -f 2>/dev/null || true
exit 0
