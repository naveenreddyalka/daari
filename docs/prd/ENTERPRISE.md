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

## Where daari stands (verified in-tree, 2026-10-01)

**Loop velocity.** Yesterday’s P1/P2 wave merged end-to-end: Anthropic
`output_config.format`, Messages server-side MCP (`mcp_servers` /
`mcp_toolset`), RFC 9728 protected-resource discovery, native `POST /v1/ocr`,
OpenAPI `/mcp/proxy`, and opt-in `GET /v1/mcp/registry.json`. Hot-reload
`config.yaml` remains in flight. Per-key tool-name allowlists for Messages
`mcp_servers` is parked (needs a longer session). Tonight’s refill targets
decision-model surfaces (Ollama systemone / Jev) and MCP OAuth depth past
discovery.

**Outward.** LiteLLM **v1.103.0** (2026-09-27): config-file ownership, Fuse +
TypeSafe JEV routing, MCP client allowlists, RFC 8693 token exchange, access-
group / project budget hardening. Portkey: Messages↔Responses routing +
server-side MCP GA path; Agent Gateway CRUD/RBAC. Kong AI Gateway **2.x /
3.12+**: MCP OAuth2 resource-server, upstream MCP aggregator, REST→MCP.
Ollama **0.35.0** GA decision models (`POST /v1/systemone`); **0.40.0-rc0**
MLX-default on Apple Silicon. OpenRouter **Jev Router** (task-difficulty
routing). vLLM Semantic Router continues MoM signal routing (watch only).

**Inward theme: decision-model control plane + MCP OAuth completeness.**
Discovery advertises protected-resource metadata, but clients still lack a
local authorize/token mint. `/mcp` tools/list is first-party only — egress
`mcp_servers` are Responses/Messages/`/mcp/proxy` paths, not a Kong-style
aggregate ingress catalog. No `/v1/systemone` facade; complexity routing is
still heuristic. `web_search_options` is noted as unsupported locally and
forwarded on L6, but local tiers can still answer without searching.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **`POST /v1/systemone` facade** — no authenticated decision-model surface | 4 | 2 | Ollama 0.35 + OpenRouter Jev | Metered local typed decisions under daari keys | Filed — P2 ([#1291](https://github.com/naveenreddyalka/daari/issues/1291)) |
| 2 | **Decision-model complexity classifier** — heuristics only; LiteLLM Fuse/JEV | 5 | 3 | LiteLLM 1.103 Fuse/JEV; OpenRouter Jev | $0 private difficulty hop before L3–L6 | Filed — P2 ([#1292](https://github.com/naveenreddyalka/daari/issues/1292)) |
| 3 | **MCP OAuth authorize/token mint** — discovery only; no local AS | 4 | 3 | LiteLLM OBO; Kong MCP OAuth2 | IDE MCP onboarding without cloud IdP | Filed — P2 ([#1293](https://github.com/naveenreddyalka/daari/issues/1293)) |
| 4 | **Aggregate `/mcp` tools/list from `mcp_servers`** — ingress catalog is first-party only | 4 | 2 | Kong MCP aggregator | One local catalog under SSRF + policy | Filed — P2 ([#1294](https://github.com/naveenreddyalka/daari/issues/1294)) |
| 5 | **`web_search_options` silent local drop** — note only; no escalate/fail-closed | 4 | 2 | OpenAI native + cloud gateways | Client-contract honesty; L6 when search required | Filed — P2 ([#1295](https://github.com/naveenreddyalka/daari/issues/1295)) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — prior cycle | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM tool entitlements | Parked (needs ≥60m session) | Parked |
| 8 | Full OBO/DCR; A2A; admin UI; Realtime/WS | 2–4 | 3–5 | LiteLLM / Portkey / Kong | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: Anthropic `output_config.format`;
Messages server-side MCP; RFC 9728 protected-resource; `POST /v1/ocr`; OpenAPI
`/mcp/proxy`; `GET /v1/mcp/registry.json`. Still verified fine: effort mapping;
MCP activity/abort; Responses `type:mcp`; Method/Name mismatch reject; client
allowlists; Helm encrypted backups; spend `--by-tool`; `server/discover` +
`_meta`; egress SSRF / OTel / retry / breaker; refreshable `secret://`;
header_policy; tools/call metering; semantic tool search; ttlMs/cacheScope;
MCP guardrails; W3C egress trace; model_group budgets; session affinity;
Prometheus `/metrics`; agent prefix L0 + opt-in L1.

---

## Path to enterprise-grade — next 5 milestones

1. **Decision-model control plane** — `/v1/systemone` facade (row 1) then optional
   classifier for tier pick (row 2), matching Jev/Fuse without leaving the laptop.
2. **MCP OAuth completeness** — authorize/token mint after RFC 9728 (row 3) so
   Cursor/Desktop can finish the challenge locally.
3. **Unified MCP ingress catalog** — aggregate egress tools on `/mcp` (row 4)
   under existing governance.
4. **Client-contract honesty** — escalate or fail-closed on `web_search_options`
   (row 5); finish hot-reload (row 6).
5. **Governance depth** — unpark per-key tool-name allowlists (row 7); OBO/DCR /
   A2A only on buyer demand (row 8).

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-01 (decision models + MCP OAuth depth)** — Prior-cycle format /
  Messages MCP / RFC 9728 / OCR / `/mcp/proxy` / registry.json merged;
  hot-reload still open; tool-name allowlist parked. Outward: LiteLLM 1.103
  Fuse/JEV + token exchange; Ollama 0.35 systemone GA; OpenRouter Jev Router;
  Kong MCP aggregator/OAuth. Filed systemone facade, decision classifier, MCP
  token mint, `/mcp` egress aggregate, web_search escalate (P2s). OBO/DCR /
  A2A held as watch.

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
  gateway enterprise depth, gateway-backend completeness, governance,
  agent-surface fidelity, Responses honesty, images/identity/FinOps, non-chat
  endpoint parity, Apache 2.0, this PRD's creation (2026-08-28).
