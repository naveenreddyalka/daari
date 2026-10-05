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

## Where daari stands (verified in-tree, 2026-10-05 late)

**Loop velocity.** Operate-gates for compact-to-fit and MCP grant fail-closed
(Grafana, grant counter, initialize refuse, token-drop stats, compare-litellm
1.104) are on `main`. Trace/doctor/http-api/cli pins for
`tokens_before` / `tokens_after` shipped. Hot-reload `config.yaml` remains in
flight. Per-key tool-name allowlists for Messages `mcp_servers` stay parked.
FinOps surface still incomplete on the local web-ui stats page and savings
report; `observability.structured_json_logs` is not yet ownership-editable.

**Outward.** LiteLLM **v1.104.0 GA** (3 Oct) still the stable competitive bar.
**v1.105.0-rc.1** (4 Oct): Microsoft 365 MCP catalog, Straiker v3 fail-closed,
`litellm.agent()` / Lens traces — watch-only, not file. Ollama **0.40** still
MLX-default rc on Apple Silicon; stable **0.35.1** systemone. Portkey / Kong
Agent Gateway GA unchanged as demand-triggered protocol peers.

**Inward theme: FinOps + container ops honesty.** Prometheus/Grafana already
expose compact token-drop and MCP grant-denied series. Laptop operators using
`daari web-ui` / `daari report` / config PATCH still cannot see or live-tune
the same loop without yaml edits + restart.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 29 | Web-ui stats for `compact_to_fit_tokens_dropped` + `mcp_grant_denied` | 3 | 1 | LiteLLM / Grafana spend + MCP 403 | Local dashboard parity with shipped Prom series | File |
| 30 | Config ownership for `observability.structured_json_logs` | 3 | 2 | LiteLLM proxy log toggle | Live PATCH for container stdout JSON without restart | File |
| 31 | Doctor tip when `structured_json_logs` is enabled | 2 | 1 | — (ops honesty) | On-box tip before SIEM scrapers miss file-only logs | File |
| 32 | Pin `compact_to_fit_tokens_dropped` in savings-report.md | 2 | 1 | LiteLLM spend docs | FinOps guide next to `daari report` | File |
| 33 | compare-litellm note for LiteLLM 1.105 RC watch | 2 | 1 | LiteLLM release notes | Honest watch bar without shipping RC features | File |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | Shipped | Shipped |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | Shipped | Shipped |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | Shipped | Shipped |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | Shipped | Shipped |
| 8 | Full DCR; A2A; admin UI; Realtime/WS; group-scoped priority; stdio MCP; M365 catalog; Lens/agent traces | 2–4 | 3–5 | Portkey / Kong / LiteLLM 1.104–1.105 | Demand-triggered | Watch |

Shipped since 2026-09-30 scan — do not re-file: compact-to-fit including
ownership, doctor, routing-tiers pin, `daari_meta`/stats, Prometheus series,
Grafana compact + token-drop panels; MCP grant fail-closed +
ownership/doctor/http-api pins + grant-denied counter + initialize refuse;
compare-litellm 1.104 GA + compact token telemetry pin; watchdog failure-list
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
2. **FinOps + container ops surface** — web-ui stats for compact token-drop /
   MCP grant-denied (row 29), structured_json_logs ownership + doctor tip
   (rows 30–31), savings-report pin (row 32).
3. **Governance depth** — unpark per-key tool-name allowlists for Messages
   `mcp_servers` (row 7) once a ≥60m session is available.
4. **LiteLLM 1.105 watch** — M365 catalog / Straiker / Lens / agent() stay
   watch-only until GA; keep compare-litellm honest (row 33).
5. **Agent protocols on demand** — full DCR, A2A, admin UI, Realtime/WS,
   group-scoped priority, stdio MCP, M365 catalog (row 8) only when a buyer asks.

Compliance non-goals (WIF depth, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-05 (FinOps + container ops)** — Landscape flat at LiteLLM 1.104 GA
  / 1.105 RC watch. Filed web-ui stats for compact token-drop + MCP
  grant-denied, structured_json_logs ownership + doctor tip, savings-report
  pin, and compare-litellm 1.105 RC watch note. Path: live config → FinOps
  surface → governance → 1.105 watch → demand-triggered.

- **2026-10-05 (operate-gates shipped)** — Marked Grafana compact, grant
  counter, initialize refuse, token-drop stats, and compare-litellm 1.104 as
  Shipped. Path retargeted to live config → governance → 1.105 watch →
  demand-triggered. Do not re-file those operate-gates.

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

- **2026-10-02 → 09-15 and earlier** — Condensed: OBO / refuse-weak-key /
  classifier doctor / config ownership; decision models + MCP OAuth depth;
  structured outputs; client honesty; MCP ops; local MCP execution;
  2026-07-28 fidelity; gateway-backend completeness; Apache 2.0; this PRD's
  creation (2026-08-28).
