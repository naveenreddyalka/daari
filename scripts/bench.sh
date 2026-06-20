#!/usr/bin/env bash
# Benchmark representative daari tiers with curl wall-clock timings.
set -euo pipefail

BASE_URL="${DAARI_BASE_URL:-http://127.0.0.1:11435}"
SAMPLES="${SAMPLES:-5}"

python3 - "$BASE_URL" "$SAMPLES" <<'PY'
import json
import statistics
import subprocess
import sys
import time
import uuid

base_url = sys.argv[1].rstrip("/")
samples = int(sys.argv[2])
endpoint = f"{base_url}/v1/chat/completions"


def call(prompt: str, headers: dict[str, str] | None = None) -> tuple[float, str]:
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": prompt}],
    }
    cmd = ["curl", "-s", endpoint, "-H", "Content-Type: application/json"]
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
l0_prompt = f"bench-l0-{uuid.uuid4().hex}"
_, _ = call(l0_prompt)
l0_ms, l0_tier = call(l0_prompt)
rows.append(("L0", l0_ms, l0_tier))

# L1 pair.
token = uuid.uuid4().hex[:10]
seed = f"Write commit message for diff: +def bench_{token}(): pass"
para = f"Please draft a commit message for this patch: +def bench_{token}(): pass"
_, _ = call(seed, headers={"X-Daari-No-Cache": "true"})
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

