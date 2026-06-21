# daari v1.1.1 Release Notes

> Date: 2026-06-20  
> Scope: Reliability and release hardening since v1.1.0

## Highlights

- **L1 semantic threshold tuned to `0.88`**
  - Default semantic similarity threshold increased to improve L1 precision and reduce weak paraphrase matches.

- **`daari context clear` restart warning**
  - Added explicit CLI warning when daemon is running, so users know in-memory cache handles must be refreshed.

- **Doctor embedding-model check**
  - `daari doctor` now validates that the L1 embedding model (`nomic-embed-text`) is available and surfaces a clear hint when missing.

- **`scripts/bench.sh` L1 validation fix**
  - Bench flow now deterministically validates both uncached and cached paths, including L1 behavior, for stable local perf checks.

- **PyPI publish workflow**
  - Added GitHub Actions publish workflow and packaging metadata updates for automated PyPI/TestPyPI releases.

## Test status

- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest`: **125 passed**
- Integration marker (`-m integration`): pass
- Benchmark marker (`-m benchmark`): pass
- `./scripts/demo.sh`: pass
- `./scripts/bench.sh`: pass

## Upgrade notes from v1.1.0

- No breaking API changes for gateway, routing, or CLI command signatures.
- Recommended after upgrade:
  - Run `daari doctor` to confirm `nomic-embed-text` is present.
  - If daemon is running and caches are cleared, restart daemon or call cache reload endpoint.
