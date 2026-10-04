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

## Where daari stands (verified in-tree, 2026-10-04)

**Loop velocity.** Compact-to-fit (ownership, doctor, routing-tiers pin,
`daari_meta`/stats, Prometheus series) and MCP grant fail-closed (ownership,
doctor, http-api pin) are on `main`. Hot-reload `config.yaml` remains in
flight. Per-key tool-name allowlists for Messages `mcp_servers` stay parked.

**Outward.** LiteLLM **v1.104.0 GA** (3 Oct): master-key enforcement, stdio MCP
off by default, native compact-to-fit, group-scoped priority routing, team
time-window reservation, JEV Auto Router. **v1.105.0-rc.1** (4 Oct, prerelease):
Microsoft 365 MCP catalog, Straiker guardrail, proxy migration — watch, not
file. Portkey Agent Gateway CRUD/RBAC; Kong **Agent Gateway GA** (A2A). Ollama
**0.40** still MLX-default rc on Apple Silicon; stable **0.35.1** systemone.

**Inward theme: operate what shipped.** Compact and MCP grant gates are live,
but Grafana has no compact panel, grant-denies blend into generic MCP deny,
`initialize` still handshakes without a grant, and token-drop FinOps is
missing. Yaml edits still need a process restart versus the PATCH ownership
path.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | File this run | File this run |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | File this run | File this run |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | File this run | File this run |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | File this run | File this run |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | File this run | File this run |
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
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | Shipped | Shipped |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | Shipped | Shipped |
| 8 | Full DCR; A2A; admin UI; Realtime/WS; group-scoped priority; stdio MCP; M365 catalog | 2–4 | 3–5 | Portkey / Kong 3.14 / LiteLLM 1.104–1.105 | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: compact-to-fit including
ownership, doctor, routing-tiers pin, `daari_meta`/stats, Prometheus series;
MCP grant fail-closed + ownership/doctor/http-api pins; watchdog failure-list
dedupe + skip-integration + sandbox hatch docs; Anthropic `output_config.format`;
Messages server-side MCP; RFC 9728; `POST /v1/ocr`; OpenAPI `/mcp/proxy`;
`GET /v1/mcp/registry.json`; `POST /v1/systemone`; decision-model classifier;
MCP OAuth authorize/token mint; `/mcp` aggregate egress; `web_search_options`
escalate / fail-closed; doctor tips for registry / aggregate / local_as /
classifier. Still verified fine: effort mapping; MCP activity/abort; Responses
`type:mcp`; Method/Name mismatch reject; client allowlists; Helm encrypted
backups; spend `--by-tool`; `server/discover` + `_meta`; egress SSRF / OTel /
retry / breaker; refreshable `secret://`; header_policy; tools/call metering;
semantic tool search; ttlMs/cacheScope; MCP guardrails; W3C egress trace;
model_group budgets; session affinity; Prometheus `/metrics`; agent prefix L0
+ opt-in L1; config ownership for prefer/budgets/cache/boundaries/classifier/MCP/compact.

---

## Path to enterprise-grade — next 5 milestones

1. **Live config reload** — finish hot-reload `config.yaml` (row 6) so yaml
   edits match the shipped ownership PATCH path without process restart.
2. **Operate shipped gates** — Grafana compact panel, grant-denied counter,
   initialize fail-closed, compact token-drop stats (rows 24–27).
3. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
4. **Honest comparison** — keep compare-litellm aligned with 1.104 GA (row 28).
5. **Agent protocols on demand** — full DCR, A2A, admin UI, Realtime/WS,
   group-scoped priority, stdio MCP, M365 catalog (row 8) only when a buyer asks.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-04 (operate shipped gates)** — Outward: LiteLLM **1.104.0 GA**
  (3 Oct); **1.105.0-rc.1** watch-only. Path retargeted to live config →
  operate compact/MCP gates (Grafana, grant counter, initialize 403, token
  drop) → governance → demand-triggered. Filed those five auto-dev items.

- **2026-10-04 (compact + MCP grant shipped)** — Marked compact ownership,
  doctor tip, routing-tiers pin, `daari_meta`/stats, and MCP grant fail-closed
  Shipped. Path was live config → governance → demand-triggered protocols.

- **2026-10-03** — Compact live-tune + MCP grant fail-closed filed then
  shipped; watchdog dedupe / skip-integration / hatch docs; http-api ownership
  pins. LiteLLM still quoted as 1.104 rc / 1.103.0 stable at that cut.

- **2026-10-02** — OBO, refuse-weak-key, classifier doctor, config ownership,
  doctor-health pins Shipped; systemone / classifier / aggregate /
  web_search escalate already on `main`.

- **2026-10-01 → 09-15 and earlier** — Condensed: decision models + MCP OAuth
  depth; structured outputs; client honesty; MCP ops; local MCP execution;
  2026-07-28 fidelity; gateway-backend completeness; Apache 2.0; this PRD's
  creation (2026-08-28).
