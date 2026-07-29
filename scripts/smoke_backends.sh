#!/usr/bin/env bash
# Live Redis + Postgres compose smoke (issue #142).
# Skips cleanly when Docker is unavailable (not required for default CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "SKIP smoke_backends.sh: Docker daemon unavailable"
  echo "Offline path still runs: python scripts/smoke_backends.py"
  exit 0
fi

echo "Starting redis + postgres (compose profile backends)…"
docker compose --profile backends up -d redis postgres

cleanup() {
  docker compose --profile backends stop redis postgres >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Waiting for health…"
for i in $(seq 1 30); do
  if docker compose --profile backends exec -T redis redis-cli ping 2>/dev/null | grep -q PONG \
    && docker compose --profile backends exec -T postgres pg_isready -U daari -d daari >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/15}"
export POSTGRES_URL="${POSTGRES_URL:-postgresql://daari:daari@127.0.0.1:5432/daari}"

# Optional extras for live clients
python -c "import redis, psycopg" 2>/dev/null || pip install -q 'redis>=5' 'psycopg[binary]>=3.1'

python scripts/smoke_backends.py
