#!/usr/bin/env bash
# daari install — venv, editable install, Ollama model hint, optional doctor
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${REPO_ROOT}/.venv"
RUN_DOCTOR="${RUN_DOCTOR:-1}"

cd "${REPO_ROOT}"

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Error: Python 3.12 required (python3.12 not found)." >&2
  echo "Install from https://www.python.org/downloads/ or your package manager." >&2
  exit 1
fi

echo "==> Creating venv at ${VENV}"
python3.12 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo "==> Installing daari (editable + dev extras)"
pip install -q -U pip
pip install -q -e ".[dev]"

if command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling default Ollama model (llama3.2:3b)"
  ollama pull llama3.2:3b || echo "Warning: ollama pull failed — run manually when Ollama is ready."
else
  echo "==> Ollama not found."
  echo "    Install from https://ollama.com then run: ollama pull llama3.2:3b"
fi

echo ""
echo "Install complete. Activate with:"
echo "  source ${VENV}/bin/activate"
echo ""
echo "Next steps:"
echo "  daari serve"
echo "  daari doctor"

if [[ "${RUN_DOCTOR}" == "1" ]]; then
  echo ""
  echo "==> Running daari doctor (optional; failures are OK before Ollama/daemon start)"
  daari doctor || true
fi
