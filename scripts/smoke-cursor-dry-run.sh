#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/daari" ]]; then
  DAARI_BIN=".venv/bin/daari"
else
  DAARI_BIN="daari"
fi

echo "[smoke-cursor-dry-run] using: ${DAARI_BIN}"
"${DAARI_BIN}" setup cursor --dry-run
echo "[smoke-cursor-dry-run] pass"
