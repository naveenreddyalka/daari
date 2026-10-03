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

## Where daari stands (verified in-tree, 2026-10-03)

**Loop velocity.** OBO egress exchange, refuse-weak-master-key, classifier-model
doctor tip, config ownership for decision/MCP knobs, and hermetic doctor-health
pins are on `main`. Local watchdog sandbox serve now sets the weak-key hatch so
KeepAlive does not crash-loop after the gate. Hot-reload `config.yaml` remains
in flight (`agent:working`). Per-key tool-name allowlists for Messages
`mcp_servers` stay parked (needs a longer session).

**Outward.** LiteLLM **v1.104.0-rc.2**: UI/CLI session tokens (`litellm_login_`
AES-GCM, header-safe) on top of **rc.1** master-key enforcement, group-scoped
priority routing, team time-window reservation, JEV Auto Router, native
compact-to-fit, MCP `object_permission` + `require_key_mcp_access_defined`.
Portkey Agent Gateway CRUD/RBAC; Kong **Agent Gateway GA** (A2A). Ollama
**0.40** MLX-default rc on Apple Silicon.

**Inward theme: live config + loop hygiene + compact-before-L6.** Ownership
leaves for classifier/MCP shipped; operators still restart for yaml edits.
Watchdog SHA-stamped duplicates steal `--pick`. LiteLLM compact-to-fit is the
next local-first spend lever before frontier escalate.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 9 | RFC 8693 OBO token exchange for egress `mcp_servers` | 4 | 3 | LiteLLM OBO / Kong MCP OAuth2 | Shipped | Shipped |
| 10 | Refuse weak/unset master key at serve (opt-out) | 3 | 2 | LiteLLM 1.104 master-key gate | Shipped | Shipped |
| 11 | Doctor tip when decision_classifier model missing from Ollama | 3 | 1 | — (local tags check) | Shipped | Shipped |
| 12 | Extend `/v1/daari/config` ownership to decision_classifier + MCP knobs | 3 | 2 | LiteLLM config ownership UI | Shipped | Shipped |
| 13 | Hermetic doctor-health pins for aggregate / local_as / classifier tips | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 14 | Watchdog: dedupe local E2E issues by failure list (not SHA) | 3 | 1 | — (loop hygiene) | File this run | File |
| 15 | Skip live integration when watchdog daemon is unreachable | 2 | 1 | — (signal quality) | File this run | File |
| 16 | Hermetic http-api pin for config ownership classifier/MCP leaves | 2 | 1 | — (docs regression) | File this run | File |
| 17 | Opt-in compact-to-fit before L6 | 3 | 2 | LiteLLM 1.104 compact-to-fit | File this run | File |
| 18 | Docs pin: watchdog sandbox master-key hatch + `--install` | 2 | 1 | — (ops honesty) | File this run | File |
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

1. **Live config reload** — finish hot-reload `config.yaml` (row 6) so yaml
   edits match the shipped ownership PATCH path without process restart.
2. **Loop hygiene** — watchdog failure-list dedupe (row 14) and skip
   integration when serve is down (row 15) so `--pick` stays on product work.
3. **Compact before L6** — opt-in compact-to-fit (row 17) as LiteLLM 1.104
   parity that keeps tokens on-box.
4. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
5. **Demand-triggered protocols** — full DCR, A2A (Kong Agent Gateway / Portkey),
   admin UI, Realtime/WS (row 8) only when a buyer asks.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-03 (live config + loop hygiene + compact)** — Marked OBO, refuse-weak-key,
  classifier-model doctor, config ownership, doctor-health pins Shipped; watchdog
  sandbox hatch on `main`. Outward: LiteLLM 1.104.0-rc.2 session tokens; rc.1
  compact-to-fit / MCP tool permissions. Filed watchdog dedupe, skip-integration
  when daemon down, http-api ownership pin, compact-to-fit, watchdog hatch docs.
  Path retargeted to live config → loop hygiene → compact-before-L6 → governance.

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
