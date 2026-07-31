# Testing

| Suite | Command | When |
|-------|---------|------|
| Default (CI) | `pytest -m "not integration and not benchmark" -q` | Before every commit |
| Live Ollama | `OLLAMA_HOST=http://127.0.0.1:11434 pytest -m integration` | Local with Ollama |
| Benchmark | `pytest -m benchmark` | Optional |
| Web UI | `cd packages/web-ui && npm test` | UI changes |
| Extension | `cd packages/browser-extension && npm test` | Extension changes |

Layout: `tests/unit/`, `tests/integration/` (ASGI gateway; Ollama mocked unless live), smokes under `scripts/smoke_*.py`.

Agent contract: [AGENTS.md](https://github.com/naveenreddyalka/daari/blob/main/AGENTS.md).
