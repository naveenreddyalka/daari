#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SETUP_CURSOR=0
if [[ "${1:-}" == "--setup-cursor" ]]; then
  SETUP_CURSOR=1
elif [[ "${1:-}" != "" ]]; then
  echo "Usage: scripts/tunnel.sh [--setup-cursor]" >&2
  exit 1
fi

if [[ -x ".venv/bin/daari" ]]; then
  DAARI_BIN=".venv/bin/daari"
else
  DAARI_BIN="daari"
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is required. Install it with: brew install cloudflared" >&2
  exit 1
fi

DAARI_PID=""
TUNNEL_PID=""
TMP_DIR="$(mktemp -d)"
DAARI_LOG="${TMP_DIR}/daari.log"
TUNNEL_LOG="${TMP_DIR}/cloudflared.log"

cleanup() {
  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    kill "${TUNNEL_PID}" >/dev/null 2>&1 || true
    wait "${TUNNEL_PID}" 2>/dev/null || true
  fi
  if [[ -n "${DAARI_PID}" ]] && kill -0 "${DAARI_PID}" >/dev/null 2>&1; then
    kill "${DAARI_PID}" >/dev/null 2>&1 || true
    wait "${DAARI_PID}" 2>/dev/null || true
  fi
  rm -rf "${TMP_DIR}"
  echo ""
  echo "Tunnel stopped. Re-run scripts/tunnel.sh to start again."
}
trap cleanup EXIT INT TERM

health_ok() {
  curl -fsS "http://127.0.0.1:11435/health" >/dev/null 2>&1
}

if health_ok; then
  echo "daari daemon already healthy on http://127.0.0.1:11435"
else
  echo "Starting daari daemon..."
  "${DAARI_BIN}" serve >"${DAARI_LOG}" 2>&1 &
  DAARI_PID="$!"
  for _ in $(seq 1 60); do
    if health_ok; then
      break
    fi
    sleep 0.5
  done
  if ! health_ok; then
    echo "daari failed health check. Last daemon logs:" >&2
    tail -n 40 "${DAARI_LOG}" >&2 || true
    exit 1
  fi
  echo "daari is healthy."
fi

echo "Starting cloudflared tunnel..."
cloudflared tunnel --url "http://127.0.0.1:11435" >"${TUNNEL_LOG}" 2>&1 &
TUNNEL_PID="$!"

TUNNEL_URL=""
for _ in $(seq 1 120); do
  if ! kill -0 "${TUNNEL_PID}" >/dev/null 2>&1; then
    echo "cloudflared exited unexpectedly. Last tunnel logs:" >&2
    tail -n 60 "${TUNNEL_LOG}" >&2 || true
    exit 1
  fi
  TUNNEL_URL="$(
    python - "${TUNNEL_LOG}" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
match = re.search(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", text)
print(match.group(0) if match else "")
PY
  )"
  if [[ -n "${TUNNEL_URL}" ]]; then
    break
  fi
  sleep 0.25
done

if [[ -z "${TUNNEL_URL}" ]]; then
  echo "Timed out waiting for cloudflared public URL. Last tunnel logs:" >&2
  tail -n 60 "${TUNNEL_LOG}" >&2 || true
  exit 1
fi

OPENAI_BASE_URL="${TUNNEL_URL}/v1"
echo ""
echo "Tunnel ready: ${TUNNEL_URL}"
echo "Cursor Override OpenAI Base URL: ${OPENAI_BASE_URL}"
echo "Inference stays local in daari; only Cursor's HTTP hop is public."
echo ""

if [[ "${SETUP_CURSOR}" == "1" ]]; then
  echo "Applying Cursor setup with tunnel base URL..."
  "${DAARI_BIN}" setup cursor --base-url "${OPENAI_BASE_URL}"
  echo ""
fi

echo "Keep this terminal open while using Cursor. Press Ctrl+C to stop."
wait "${TUNNEL_PID}"
