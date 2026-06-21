# daari v1.0 Release Checklist

> Date: 2026-06-21  
> Scope: v1.0 readiness gate for local-first core + C3 provider parity + E1 runtime scaffold

## Features done

- [x] Local-first routing chain: `L0` -> `CCS` -> `L1` -> `L2`/`Lt` -> `L3`/`L4`/`L5` -> optional `L6`
- [x] OpenAI-compatible chat gateway and Anthropic-compatible messages gateway (stream + non-stream)
- [x] MCP ingress with `tools/list` and `tools/call`
- [x] MCP `tools/call` input schema validation with structured error codes
- [x] C3 integration providers: Sourcegraph + GitHub Enterprise + GitLab self-hosted (`@gitlab`)
- [x] Router integration trigger mapping from config (`integrations.<provider>.triggers`)
- [x] E1 enterprise runtime scaffold: org settings, org cache path resolver, `daari serve --org <id>`, `DAARI_ORG_ID`
- [x] Doctor org check for enterprise activation validity
- [x] Setup and developer workflow commands (`setup`, `doctor`, `install`, `context clear`)
- [x] GP-01 through GP-20 routing eval coverage passing

## Known gaps (deferred post-v1.0)

- [ ] Enterprise E2 shared cache service (remote/org cache network service) not implemented
- [ ] Enterprise E3 collective learning and control plane sync not implemented
- [ ] Live token-backed Sourcegraph/GHE/GitLab smoke in CI is not possible without org credentials
- [ ] Optional L4/L5 model auto-pull remains user-controlled
- [ ] Browser extension and web UI remain scaffolds

## Install path

```bash
git clone https://github.com/naveenreddyalka/daari
cd daari
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ollama pull llama3.2:3b
daari doctor
daari serve
```

## Test commands

```bash
.venv/bin/python -m pytest
OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -m integration
.venv/bin/python -m pytest -m benchmark
./scripts/demo.sh
./scripts/bench.sh
```

## Manual smoke checklist

- [x] `@gitlab` trigger routes to `integration:gitlab`
- [x] `tools/call` invalid input returns `MCP_ERR_SCHEMA_VALIDATION`
- [x] `daari serve --org acme` uses org-scoped cache root
