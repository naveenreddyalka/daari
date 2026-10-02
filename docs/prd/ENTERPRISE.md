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

## Where daari stands (verified in-tree, 2026-10-02)

**Loop velocity.** Decision-model + MCP OAuth mint / aggregate / web_search
escalate wave is on `main` (`POST /v1/systemone`, opt-in complexity classifier,
local AS token mint, `/mcp` egress tools/list aggregate, web_search escalate-
or-fail-closed). Doctor tips + hermetic doc pins for that wave are draining.
Hot-reload `config.yaml` remains in flight. Per-key tool-name allowlists for
Messages `mcp_servers` stay parked (needs a longer session).

**Outward.** LiteLLM **v1.103.0** (config ownership, Fuse/JEV, MCP allowlists,
RFC 8693 token exchange) plus **v1.104.0-rc1**: refuse weak/unset master key,
group-scoped priority routing, team time-window reservation, JEV classifier for
Auto Router, native compact-to-fit. Portkey: Agent Gateway CRUD/RBAC GA path;
MCP Gateway claim auth (tool-level coming). Kong AI Gateway **3.12+ / 3.14**:
MCP aggregator + OAuth2 resource-server; **Agent Gateway GA** (A2A). Ollama
**0.35** systemone decision models; **0.40.0-rc0** MLX-default on Apple Silicon.
OpenRouter **typesafe/jev-router** (difficulty + cache-aware model/effort stickiness).

**Inward theme: governance depth + config live-edit.** Local AS mint and
egress aggregate closed the discovery→token gap for laptop MCP. Next friction
is IdP OBO exchange for egress `mcp_servers` (LiteLLM parity), refuse-weak-
master-key at serve (LiteLLM 1.104), doctor honesty when the classifier model
is not pulled, and extending `/v1/daari/config` ownership to the new
decision/MCP knobs so operators can live-tune beside hot-reload.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — prior cycle | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM tool entitlements | Parked (needs ≥60m session) | Parked |
| 9 | RFC 8693 OBO token exchange for egress `mcp_servers` | 4 | 3 | LiteLLM OBO / Kong MCP OAuth2 | File this run | File |
| 10 | Refuse weak/unset master key at serve (opt-out) | 3 | 2 | LiteLLM 1.104 master-key gate | File this run | File |
| 11 | Doctor tip when decision_classifier model missing from Ollama | 3 | 1 | — (local tags check) | File this run | File |
| 12 | Extend `/v1/daari/config` ownership to decision_classifier + MCP knobs | 3 | 2 | LiteLLM config ownership UI | File this run | File |
| 13 | Hermetic doctor-health pins for aggregate / local_as / classifier tips | 2 | 1 | — (docs regression) | File this run | File |
| 8 | Full DCR; A2A; admin UI; Realtime/WS | 2–4 | 3–5 | Portkey Agent GW / Kong 3.14 | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: Anthropic `output_config.format`;
Messages server-side MCP; RFC 9728 protected-resource; `POST /v1/ocr`; OpenAPI
`/mcp/proxy`; `GET /v1/mcp/registry.json`; `POST /v1/systemone`; decision-model
complexity classifier; MCP OAuth authorize/token mint; `/mcp` aggregate egress
tools/list; `web_search_options` escalate / fail-closed; doctor tips for
registry / aggregate / local_as / classifier. Still verified fine: effort
mapping; MCP activity/abort; Responses `type:mcp`; Method/Name mismatch reject;
client allowlists; Helm encrypted backups; spend `--by-tool`; `server/discover`
+ `_meta`; egress SSRF / OTel / retry / breaker; refreshable `secret://`;
header_policy; tools/call metering; semantic tool search; ttlMs/cacheScope;
MCP guardrails; W3C egress trace; model_group budgets; session affinity;
Prometheus `/metrics`; agent prefix L0 + opt-in L1; config ownership MVP for
prefer/budgets/cache/boundaries.

---

## Path to enterprise-grade — next 5 milestones

1. **Live config reload** — finish hot-reload `config.yaml` (row 6) and extend
   ownership leaves for decision/MCP knobs (row 12) so operators change
   policies without restart.
2. **Egress OBO** — RFC 8693 token exchange for `mcp_servers` (row 9) so IdP
   JWTs become scoped upstream MCP credentials on-box.
3. **Serve hardening** — refuse weak/unset master keys with explicit sandbox
   opt-out (row 10); doctor tips for missing classifier models (row 11).
4. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
5. **Demand-triggered protocols** — full DCR, A2A (Kong Agent Gateway / Portkey),
   admin UI, Realtime/WS (row 8) only when a buyer asks.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-02 (governance + serve hardening scan)** — Prior morning wave
  (systemone / classifier / local AS / aggregate / web_search escalate) verified
  on `main`; hot-reload still Open; tool-name allowlist parked. Outward: LiteLLM
  1.104-rc1 weak-master-key + team routing; Portkey Agent Gateway; Kong Agent
  Gateway GA; OpenRouter jev-router stickiness; Ollama 0.40 MLX-rc. Filed OBO
  egress exchange, refuse-weak-master-key, doctor missing-classifier-model,
  config ownership extension, hermetic doctor-health pins. Path retargeted to
  live config → OBO → serve hardening → governance → demand-triggered.

- **2026-10-02 (web_search escalate + MCP P2 wave)** — Marked systemone /
  decision classifier / MCP OAuth mint / `/mcp` aggregate / web_search
  escalate/fail-closed Shipped; hot-reload still Open; tool-name allowlist
  parked. Path was hot-reload → governance → demand-triggered protocols.

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
