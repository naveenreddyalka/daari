#!/usr/bin/env bash
# Benchmark representative daari tiers with curl wall-clock timings.
set -euo pipefail

BASE_URL="${DAARI_BASE_URL:-http://127.0.0.1:11435}"
SAMPLES="${SAMPLES:-5}"
# Daemons exposed via tunnel enforce API-key auth (issue #86); pick the key
# up from the env or the local config so the bench works either way.
API_KEY="${DAARI_API_KEY:-$(python3 -c "
import pathlib, yaml
path = pathlib.Path.home() / '.daari' / 'config.yaml'
try:
    print((yaml.safe_load(path.read_text()) or {}).get('server', {}).get('api_key', ''))
except FileNotFoundError:
    print('')
" 2>/dev/null || true)}"

API_KEY="$API_KEY" python3 - "$BASE_URL" "$SAMPLES" <<'PY'
import json
import os
import statistics
import subprocess
import sys
import time
import uuid

base_url = sys.argv[1].rstrip("/")
samples = int(sys.argv[2])
endpoint = f"{base_url}/v1/chat/completions"
api_key = os.environ.get("API_KEY", "").strip()


def call(prompt: str, headers: dict[str, str] | None = None) -> tuple[float, str]:
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": prompt}],
    }
    # daari_meta is opt-in since the Cursor BYOK compat work — the tier
    # column comes back empty without this header.
    cmd = [
        "curl", "-s", endpoint,
        "-H", "Content-Type: application/json",
        "-H", "X-Daari-Meta: true",
    ]
    if api_key:
        cmd += ["-H", f"x-api-key: {api_key}"]
    for key, value in (headers or {}).items():
        cmd += ["-H", f"{key}: {value}"]
    cmd += ["-d", json.dumps(payload)]
    started = time.perf_counter()
    out = subprocess.check_output(cmd, text=True)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    data = json.loads(out)
    tier = data.get("daari_meta", {}).get("tier", "error")
    return elapsed_ms, tier


rows: list[tuple[str, float, str]] = []

# L3 sample from uncached unique prompt.
prompt = f"bench-l3-{uuid.uuid4().hex[:8]}"
l3_ms, l3_tier = call(prompt, headers={"X-Daari-No-Cache": "true"})
rows.append(("L3", l3_ms, l3_tier))

# L0 sample from explicit warm + repeat.
l0_prompt = f"Count the characters in token {uuid.uuid4().hex} and return only the number."
l0_headers = {"X-Daari-Tier-Override": "L3"}
_, _ = call(l0_prompt, headers=l0_headers)
l0_ms, l0_tier = call(l0_prompt, headers=l0_headers)
rows.append(("L0", l0_ms, l0_tier))

# L1 pair.
seed = ""
para = ""
for _ in range(8):
    token = uuid.uuid4().hex[:10]
    candidate_seed = f"Write a commit message for this diff: +def bench_{token}(): pass"
    candidate_para = f"Draft a commit message for this diff: +def bench_{token}(): pass"
    _, first_tier = call(candidate_seed)
    if first_tier == "L3":
        seed = candidate_seed
        para = candidate_para
        break
if not seed:
    token = uuid.uuid4().hex[:10]
    seed = f"Write a commit message for this diff: +def bench_{token}(): pass"
    para = f"Draft a commit message for this diff: +def bench_{token}(): pass"
    _, _ = call(seed)
l1_ms, l1_tier = call(para)
rows.append(("L1", l1_ms, l1_tier))

# L2.
l2_ms, l2_tier = call("Format as JSON: {foo: 1, bar: two}")
rows.append(("L2", l2_ms, l2_tier))

# Lt.
lt_times = []
lt_tier = "unknown"
for _ in range(samples):
    ms, t = call("git status", headers={"X-Daari-ReRun-Command": "true", "X-Daari-No-Cache": "true"})
    lt_times.append(ms)
    lt_tier = t
rows.append(("Lt", statistics.median(lt_times), lt_tier))

print(f"Bench base URL: {base_url}")
for name, ms, tier in rows:
    print(f"{name:>2} tier={tier:<4} p50_ms={ms:.1f}")
PY

