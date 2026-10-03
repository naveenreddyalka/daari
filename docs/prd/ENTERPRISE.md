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

**Loop velocity.** Morning compact-to-fit, watchdog failure-list dedupe, skip
live integration when serve is down, http-api ownership pins, and watchdog
sandbox hatch docs are on `main`. Hot-reload `config.yaml` remains in flight.
Per-key tool-name allowlists for Messages `mcp_servers` stay parked (needs a
longer session). Compact knobs exist in yaml but not on the config-editor
ownership map, so operators still restart to live-tune spend.

**Outward.** LiteLLM **v1.104.0-rc.2** (session tokens `litellm_login_` AES-GCM)
on **rc.1**: master-key gate, group-scoped priority routing, team time-window
reservation, JEV Auto Router, native compact-to-fit, MCP `object_permission` +
`require_key_mcp_access_defined`. Portkey Agent Gateway CRUD/RBAC; Kong **Agent
Gateway GA** (A2A). Ollama **0.40** MLX-default rc on Apple Silicon. No newer
stable LiteLLM than **1.103.0** (27 Sep).

**Inward theme: compact live-tune + MCP grant fail-closed.** Compact-to-fit
ships default-off but GET/PATCH ownership, doctor, `daari_meta`, and
routing-tiers docs still treat it as invisible. Ingress `/mcp` still lists the
full catalog for virtual keys with no `metadata.mcp` grant — LiteLLM’s
require-defined MCP access is the local-first gate we can ship without unparking
per-tool Messages allowlists.

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
| 14 | Watchdog: dedupe local E2E issues by failure list (not SHA) | 3 | 1 | — (loop hygiene) | Shipped | Shipped |
| 15 | Skip live integration when watchdog daemon is unreachable | 2 | 1 | — (signal quality) | Shipped | Shipped |
| 16 | Hermetic http-api pin for config ownership classifier/MCP leaves | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 17 | Opt-in compact-to-fit before L6 | 3 | 2 | LiteLLM 1.104 compact-to-fit | Shipped | Shipped |
| 18 | Docs pin: watchdog sandbox master-key hatch + `--install` | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | File this run | File |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | File this run | File |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | File this run | File |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | File this run | File |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | File this run | File |
| 8 | Full DCR; A2A; admin UI; Realtime/WS | 2–4 | 3–5 | Portkey Agent GW / Kong 3.14 | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: compact-to-fit; watchdog
failure-list dedupe + skip-integration + sandbox hatch docs; Anthropic
`output_config.format`; Messages server-side MCP; RFC 9728; `POST /v1/ocr`;
OpenAPI `/mcp/proxy`; `GET /v1/mcp/registry.json`; `POST /v1/systemone`;
decision-model classifier; MCP OAuth authorize/token mint; `/mcp` aggregate
egress; `web_search_options` escalate / fail-closed; doctor tips for registry /
aggregate / local_as / classifier. Still verified fine: effort mapping; MCP
activity/abort; Responses `type:mcp`; Method/Name mismatch reject; client
allowlists; Helm encrypted backups; spend `--by-tool`; `server/discover` +
`_meta`; egress SSRF / OTel / retry / breaker; refreshable `secret://`;
header_policy; tools/call metering; semantic tool search; ttlMs/cacheScope;
MCP guardrails; W3C egress trace; model_group budgets; session affinity;
Prometheus `/metrics`; agent prefix L0 + opt-in L1; config ownership MVP for
prefer/budgets/cache/boundaries/classifier/MCP.

---

## Path to enterprise-grade — next 5 milestones

1. **Live config reload** — finish hot-reload `config.yaml` (row 6) so yaml
   edits match the shipped ownership PATCH path without process restart.
2. **Compact live-tune** — ownership (row 19), doctor (row 20), docs pin
   (row 21), and `daari_meta`/stats (row 22) so compact-to-fit is operable,
   not just a yaml flag.
3. **MCP grant fail-closed** — opt-in require-defined MCP access (row 23) as
   LiteLLM 1.104 parity without unparking per-tool Messages allowlists.
4. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
5. **Demand-triggered protocols** — full DCR, A2A (Kong Agent Gateway / Portkey),
   admin UI, Realtime/WS (row 8) only when a buyer asks.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-03 (compact live-tune + MCP grant fail-closed)** — Marked compact-to-fit,
  watchdog dedupe / skip-integration / hatch docs, and http-api ownership pins
  Shipped. Outward: LiteLLM 1.104.0-rc.2 still current RC; 1.103.0 latest
  stable. Filed compact ownership, doctor tip, routing-tiers pin,
  `daari_meta`/stats, and opt-in MCP grant fail-closed. Path retargeted to live
  config → compact live-tune → MCP grant gate → governance → demand-triggered.

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

- **2026-09-29 → 09-15 and earlier** — Condensed: client honesty, MCP ops,
  local MCP execution, 2026-07-28 fidelity, MCP gateway enterprise depth,
  gateway-backend completeness, governance, agent-surface fidelity, Responses
  honesty, images/identity/FinOps, non-chat endpoint parity, Apache 2.0, this
  PRD's creation (2026-08-28).
