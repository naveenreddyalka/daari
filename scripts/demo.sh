#!/usr/bin/env bash
# One-command daari demo: install deps, serve, smoke curl, stats, setup dry-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${REPO_ROOT}/.venv"
HOST="${DAARI_HOST:-127.0.0.1}"
PORT="${DAARI_PORT:-11435}"
BASE_URL="http://${HOST}:${PORT}"
SERVE_PID=""

cleanup() {
  if [[ -n "${SERVE_PID}" ]] && kill -0 "${SERVE_PID}" 2>/dev/null; then
    kill "${SERVE_PID}" 2>/dev/null || true
    wait "${SERVE_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "${REPO_ROOT}"

echo "==> Checking Python 3.12"
if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Error: python3.12 required." >&2
  exit 1
fi

if [[ ! -d "${VENV}" ]]; then
  echo "==> Creating venv"
  python3.12 -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo "==> Installing daari (editable + dev)"
pip install -q -U pip
pip install -q -e ".[dev]"

daemon_up() {
  curl -sf "${BASE_URL}/health" >/dev/null 2>&1
}

if ! daemon_up; then
  echo "==> Starting daari serve (background)"
  daari serve &
  SERVE_PID=$!
  for _ in $(seq 1 30); do
    if daemon_up; then
      break
    fi
    sleep 0.5
  done
  if ! daemon_up; then
    echo "Error: daemon did not become ready at ${BASE_URL}" >&2
    exit 1
  fi
else
  echo "==> Daemon already running at ${BASE_URL}"
fi

echo "==> Smoke test (first request — expect L3 or cache miss)"
FIRST=$(curl -sf "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi in one word"}]}' \
  || true)
if [[ -z "${FIRST}" ]]; then
  echo "Warning: chat completion failed — is Ollama running with llama3.2:3b?"
else
  echo "${FIRST}" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  tier:', d.get('daari_meta',{}).get('tier','?'))"
fi

echo "==> Repeat request (expect L0 cache hit if first succeeded)"
SECOND=$(curl -sf "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi in one word"}]}' \
  || true)
if [[ -n "${SECOND}" ]]; then
  echo "${SECOND}" | python3 -c "import json,sys; d=json.load(sys.stdin); print('  tier:', d.get('daari_meta',{}).get('tier','?'))"
fi

echo "==> Stats"
curl -sf "${BASE_URL}/v1/daari/stats" | python3 -m json.tool || daari stats 2>/dev/null || true

echo "==> Setup dry-run (Cursor)"
daari setup cursor --dry-run 2>/dev/null || echo "  (skipped — Cursor not detected or not configured)"

echo ""
echo "Demo complete. Daemon at ${BASE_URL}/v1"
if [[ -n "${SERVE_PID}" ]]; then
  echo "Started by this script — will stop on exit."
else
  echo "Using existing daemon."
fi
