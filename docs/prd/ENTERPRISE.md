# daari — Enterprise gap scan (living PRD)

> Maintained by the daily **prd-cycle** automation ([docs/automations/prd-cycle.md](../automations/prd-cycle.md)).
> Mandate: fastest credible path to a production-grade router enterprises run
> instead of LiteLLM, Portkey, Kong AI Gateway, or a cloud gateway — and keep
> the `auto-dev` backlog fed with the next most valuable work.
> Scoring: impact 1–5 (adoption/retention weight), effort 1–5 (subsystems touched,
> invasiveness). Priority label = impact − effort (≥3 → P1, 1–2 → P2, ≤0 → P3).
> Keep under ~300 lines; prune rows that ship or go stale.
> Phase-E org cache/learning spec: [phase-e-enterprise.md](phase-e-enterprise.md).

---

## Where daari stands (verified in-tree, 2026-09-30)

**Loop velocity.** Yesterday’s P1/P2 wave merged: Anthropic `output_config.effort`,
MCP activity + force-abort, Responses server-side MCP, Method/Name mismatch
reject, per-key MCP client allowlists, scheduled encrypted backups, spend
`--by-tool`. Hot-reload `config.yaml` remains the only mid-priority feature
still in flight. Tonight’s backlog refill targets client-contract honesty and
the LiteLLM/Portkey MCP enterprise bar that stayed on watch.

**Outward.** LiteLLM **v1.103.1** stable + **v1.104.0-rc.2** / **v1.105.0-dev.1**:
MCP OAuth discovery + registry, native OCR default, `/mcp/proxy` schema
discovery, tool-permission guardrails with param patterns. Portkey **v2.20**
unified gateway + server-side MCP on Responses *and* Messages. Kong AI Gateway
**2.1+** still the 2026-07-28 Method/Name / `server/discover` reference (daari
parity shipped). Anthropic stabilized structured outputs under
`output_config.format` (effort already mapped). Ollama **0.35.0** adds
`/v1/systemone` decision models; **0.35.1-rc0** / **0.40.0-rc0** pre. vLLM
**0.30.0**; llama.cpp **0.5.0** / rolling builds.

**Inward theme: structured-output honesty + MCP enterprise depth.**
`output_config.effort` ships, but `output_config.format` is still ignored for
local `json_schema` (legacy `output_format` only). Messages has no server-side
MCP (`mcp_servers` / `mcp_toolset`); Portkey does. No RFC 9728 protected-resource
metadata for `/mcp`. No native `/v1/ocr`. No OpenAPI→MCP proxy discovery.
Ollama decision models and A2A/admin UI stay watch.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **`output_config.format` structured outputs** — local json_schema only reads legacy `output_format` | 5 | 1 | Anthropic stable + LiteLLM mapping | Local L3–L5 schema answers without frontier | Filed — P1 ([#1260](https://github.com/naveenreddyalka/daari/issues/1260)) |
| 2 | **Messages server-side MCP** — `mcp_servers` + `mcp_toolset` ignored; Responses-only today | 5 | 3 | Portkey Messages + Responses | Reuse egress SSRF + metering on Claude path | Filed — P2 ([#1261](https://github.com/naveenreddyalka/daari/issues/1261)) |
| 3 | **RFC 9728 protected-resource for `/mcp`** — no OAuth discovery / WWW-Authenticate | 4 | 3 | LiteLLM MCP OAuth | Local IdP metadata; Cursor/Desktop onboarding | Filed — P2 ([#1262](https://github.com/naveenreddyalka/daari/issues/1262)) |
| 4 | **Native `POST /v1/ocr`** — images exist; no OCR modality | 4 | 3 | LiteLLM OCR default | Local vision first, L6 OCR fallback | Filed — P2 ([#1263](https://github.com/naveenreddyalka/daari/issues/1263)) |
| 5 | **`/mcp/proxy` OpenAPI schema discovery** — tools only from first-party + egress ids | 3 | 2 | LiteLLM / Kong conversion-listener | Private OpenAPI → MCP under SSRF policy | Filed — P2 ([#1264](https://github.com/naveenreddyalka/daari/issues/1264)) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM / cloud CPs | Open — prior cycle | Open |
| 7 | Ollama `/v1/systemone` decision facade; MCP registry.json; A2A; admin UI | 2–4 | 2–5 | Ollama / LiteLLM / Portkey | Demand-triggered | Watch |

Shipped since 2026-09-29 scan — do not re-file: Anthropic `output_config.effort`;
MCP in-flight activity + admin force-abort; Responses `type:mcp` server-side
execution; `Mcp-Method`/`Mcp-Name` body mismatch reject; per-key/team MCP client
allowlists; Helm scheduled encrypted backups; `daari spend report --by-tool`.
Still verified fine: `server/discover` + `_meta`; MCP egress SSRF / OTel / retry /
breaker; refreshable `secret://`; Helm `header_policy`; tools/call metering +
`mcp` rate family; tool allow/deny + audit; semantic tool search; ttlMs/cacheScope;
MCP guardrails; W3C egress trace; oauth `secret://` re-mint; encrypt↔decrypt
restore; lifetime + weekly/rpw budgets.

---

## Path to enterprise-grade — next 5 milestones

1. **Structured-output honesty** — honor `output_config.format` (row 1) so modern
   Anthropic SDKs get schema-constrained local answers, not silent drops.
2. **Messages MCP parity** — server-side `mcp_servers` / `mcp_toolset` (row 2)
   matching Portkey on the Claude Code path.
3. **MCP OAuth discovery** — RFC 9728 protected-resource + challenge (row 3)
   so IDE MCP clients can onboard without inventing API-key UX.
4. **Document modality** — native `/v1/ocr` (row 4) beside images for local-first
   doc agents.
5. **OpenAPI→MCP proxy** (row 5) + finish hot-reload (row 6); then systemone /
   registry / A2A (row 7) on buyer demand.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-30 (structured outputs + MCP enterprise depth)** — Prior-cycle
  effort / MCP ops / Responses MCP / Method-Name / allowlists / backups /
  `--by-tool` merged; hot-reload still open. Outward: LiteLLM 1.103.1+ OCR /
  OAuth / `/mcp/proxy`; Portkey Messages server-side MCP; Anthropic
  `output_config.format`; Ollama 0.35 decision models. Filed format honesty
  (P1), Messages server-side MCP, RFC 9728 discovery, `/v1/ocr`, `/mcp/proxy`
  (P2s). Systemone / registry / A2A held as watch.

- **2026-09-29 (client honesty + MCP ops + local MCP execution)** — Overnight
  discover/SSRF and morning resilience/secrets/Helm merged. Filed effort
  passthrough (P1), MCP activity/abort, Responses server-side MCP, header
  mismatch reject, config hot-reload (P2s). Client allowlists / backups /
  `--by-tool` filed then merged 09-29/09-30.

- **2026-09-28 → 09-15 and earlier** — Condensed: 2026-07-28 fidelity, MCP
  gateway enterprise depth, fleet-backend completeness, governance,
  agent-surface fidelity, Responses honesty, images/identity/FinOps, non-chat
  endpoint parity, Apache 2.0, this PRD's creation (2026-08-28).
