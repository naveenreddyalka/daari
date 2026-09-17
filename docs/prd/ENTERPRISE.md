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

## Where daari stands (verified in-tree, 2026-09-17)

Evening drain closed the afternoon refill: Helm orgPool wiring, ServiceMonitor
bearer auth, Grafana backend-pool + concurrency panels, doctor Redis + `/ready`,
and hard-reject hermetic burst all merged. Prior fleet/RBAC/ops rows remain on
`main`.

**Positioning:** LiteLLM v1.101.0 is the outward bar (heuristic auto-router,
semantic MCP tool search, optional Prometheus metrics port / multiproc, GenAI
OTLP). Portkey / Kong / OpenRouter quiet on net-new gateway surfaces. Competitive
delta stays inward: local stats/web-ui parity for soft/hard rejects, scrape-only
metrics listen port, install NOTES honesty, doctor metrics-auth advisory, and
hermetic 402 budget/quota burst coverage.

**Inward theme:** Stats + web-ui soft_warnings/rejects, optional metrics scrape
port, Helm NOTES for ServiceMonitor bearer + orgPool, doctor metrics auth warn,
hermetic hard 402 budget/request-quota burst.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Stats + web-ui soft/hard rejects** — Grafana has panels; `/v1/daari/stats` silent | 3 | 2 | LiteLLM dashboard | Local cliff visibility without Prometheus | **File** (P2) |
| 2 | **Optional metrics scrape port** — `/metrics` only on API port + api_key | 3 | 2 | LiteLLM `--prometheus_metrics_port` | Private scrapes without Bearer on every monitor | **File** (P2) |
| 3 | **Helm NOTES bearer + orgPool** — chart features shipped; NOTES omit them | 2 | 1 | Helm ecosystem | Install-time hints catch dark scrapes / unused pool | **File** (P3) |
| 4 | **Doctor metrics auth advisory** — api_key locks `/metrics`; doctor quiet | 2 | 1 | Portkey health | Warn before kube scrapes go 401 | **File** (P3) |
| 5 | **Hermetic hard 402 burst** — 429 guarded; budget/quota 402 not | 2 | 1 | LiteLLM | Catch 402 reject-path regressions under load | **File** (P3) |
| 6 | **Access-group budgets / MCP introspect / OTLP GenAI / multiproc** — LiteLLM deltas | 3 | 4 | LiteLLM | Watch until local demand | Watch |
| 7 | **WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

Pruned this run: orgPool wiring, ServiceMonitor bearer, Grafana pool/concurrency,
doctor Redis+/ready, hard-reject hermetic (all shipped afternoon→evening).

---

## Path to enterprise-grade — next 5 milestones

1. **Local cliff visibility** — soft_warnings / rejects on stats + web-ui.
2. **Scrape-only metrics port** — optional internal listener without inference auth.
3. **Install-time chart honesty** — NOTES for bearer scrapes and orgPool.
4. **Doctor metrics auth** — warn when master key locks `/metrics`.
5. **Hermetic 402 path** — budget and request-quota bursts stay ceiling-guarded.

---

## Changelog

- **2026-09-17 (evening)** — Afternoon refill drained. Outward: LiteLLM v1.101.0
  (heuristic auto-router, semantic MCP search, metrics port) still the bar; no
  net-new Kong/Portkey gateway surfaces. Inward stats/web-ui, scrape port, NOTES,
  doctor metrics-auth, and hermetic 402 burst; filing five issues.
- **2026-09-17 (afternoon)** — Morning refill drained (ServiceMonitor → TTFT
  hermetic). Outward: LiteLLM Prometheus multiproc / metrics-port still the
  bar; no net-new Kong/Portkey gateway surfaces. Inward chart/doctor/dashboard
  audit; filing five issues (orgPool wiring, ServiceMonitor auth, Grafana
  pool/concurrency, doctor Redis+/ready, hard-reject hermetic).
- **2026-09-17 (morning)** — Drain shipped night ops/RBAC + facade/bench rows.
  Backlog empty; refilled five issues (ServiceMonitor, Grafana TTFT preference,
  analyst config GET, ChatGPT Desktop caps docs, TTFT preference hermetic).
  Outward: LiteLLM v1.100.1 still stable bar; facade capabilities matched
  Ollama 0.34 reporting in-tree.
- **2026-09-16 (night)** — Delta scan: LiteLLM v1.103.0-dev.1 still fixes-only;
  Ollama v0.34.2-rc0 llama.cpp-only; Portkey/Kong/vLLM/OpenRouter flat. Inward
  ops/RBAC audit after dry-run ship; filed five issues (hard-reject metrics,
  version exposure, rate-limit degraded gauge, Helm securityContext+PDB, SSO
  RBAC leftovers). Pruned shipped route dry-run row.
- **2026-09-16 (late)** — Delta scan: LiteLLM v1.103.0-dev.1 fixes-only;
  Ollama v0.34.1 stable (capability reporting, faster `/api/tags`); rest flat.
  Inward fleet-auth audit; filed five issues (Postgres keys/teams, Helm
  graceful rollout, team RPM/TPM, keys export/import, facade capabilities).
  Pruned shipped Grafana soft-warn row.
- **2026-09-16 (evening→08-28)** — Condensed prior drains (soft-warn, TTFT,
  Redis resilience, tenancy, batches, Kong parity, Apache 2.0, this PRD).
