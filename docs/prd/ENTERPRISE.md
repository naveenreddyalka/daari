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

**Loop velocity.** The decision-model + MCP OAuth / aggregate / web_search wave
merged: `POST /v1/systemone`, opt-in complexity classifier, local OAuth
authorize/token mint, `/mcp` egress tools/list aggregate, and
`web_search_options` escalate-or-fail-closed (no silent local drop). Follow-on
docs/doctor tips for registry and escalate hermetic pins also landed.
Hot-reload `config.yaml` remains in flight. Per-key tool-name allowlists for
Messages `mcp_servers` stays parked (needs a longer session).

**Outward.** LiteLLM **v1.103.0** (2026-09-27): config-file ownership, Fuse +
TypeSafe JEV routing, MCP client allowlists, RFC 8693 token exchange, access-
group / project budget hardening. Portkey: Messages↔Responses routing +
server-side MCP GA path; Agent Gateway CRUD/RBAC. Kong AI Gateway **2.x /
3.12+**: MCP OAuth2 resource-server, upstream MCP aggregator, REST→MCP.
Ollama **0.35.0** GA decision models (`POST /v1/systemone`); **0.40.0-rc0**
MLX-default on Apple Silicon. OpenRouter **Jev Router** (task-difficulty
routing). vLLM Semantic Router continues MoM signal routing (watch only).

**Inward theme: config hot-reload + governance depth.** Decision-model control
plane and MCP OAuth completeness past discovery are in-tree (opt-in). `/mcp`
can aggregate egress `mcp_servers` into the ingress catalog. Chat
`web_search_options` escalates to L6 when frontier is available, or fails
closed — never a silent local answer. Remaining enterprise friction is live
`config.yaml` reload without restart, then unparking per-key tool-name
allowlists and deeper OBO/DCR only on buyer demand.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — prior cycle | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM tool entitlements | Parked (needs ≥60m session) | Parked |
| 8 | Full OBO/DCR; A2A; admin UI; Realtime/WS | 2–4 | 3–5 | LiteLLM / Portkey / Kong | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: Anthropic `output_config.format`;
Messages server-side MCP; RFC 9728 protected-resource; `POST /v1/ocr`; OpenAPI
`/mcp/proxy`; `GET /v1/mcp/registry.json`; `POST /v1/systemone` (#1291);
decision-model complexity classifier (#1292); MCP OAuth authorize/token mint
(#1293); `/mcp` aggregate egress tools/list (#1294); `web_search_options`
escalate / fail-closed (#1295). Still verified fine: effort mapping; MCP
activity/abort; Responses `type:mcp`; Method/Name mismatch reject; client
allowlists; Helm encrypted backups; spend `--by-tool`; `server/discover` +
`_meta`; egress SSRF / OTel / retry / breaker; refreshable `secret://`;
header_policy; tools/call metering; semantic tool search; ttlMs/cacheScope;
MCP guardrails; W3C egress trace; model_group budgets; session affinity;
Prometheus `/metrics`; agent prefix L0 + opt-in L1.

---

## Path to enterprise-grade — next 5 milestones

1. **Live config reload** — finish hot-reload `config.yaml` (row 6) so operators
   change policies without restart, matching LiteLLM config ownership locally.
2. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
3. **Demand-triggered protocols** — OBO/DCR, A2A, admin UI, Realtime/WS (row 8)
   only when a buyer asks; do not preempt the loop.
4. **Decision-model polish** — keep systemone + classifier opt-in paths
   hermetic in docs/doctor as Ollama/OpenRouter Jev evolve (watch outward).
5. **MCP catalog honesty** — keep aggregate egress + local AS discoverable and
   tested as IDE clients harden OAuth/MCP onboarding.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-02 (web_search escalate + MCP P2 wave)** — Marked #1291–#1295
  Shipped (systemone, decision classifier, MCP OAuth mint, `/mcp` aggregate,
  web_search escalate/fail-closed); hot-reload still Open; tool-name allowlist
  parked. Inward theme no longer calls web_search a silent local drop. Path
  retargeted to hot-reload → governance → demand-triggered protocols.

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
