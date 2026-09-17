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

Afternoon drain closed the morning refill: Helm ServiceMonitor, Grafana TTFT
preference panel, SSO analyst GET config, ChatGPT Desktop capability docs, and
TTFT preference hermetic burst all merged. Prior fleet/RBAC/ops rows remain on
`main`.

**Positioning:** LiteLLM still the outward bar (Prometheus multiproc / optional
metrics port, Grafana GenAI OTLP). Ollama capability reporting matched in-tree.
Portkey / Kong / OpenRouter quiet on net-new gateway surfaces. Competitive
delta stays inward: chart/env honesty, scrape auth under API key, doctor
readiness, dashboard parity for pool/concurrency.

**Inward theme:** Wire unused Helm `orgPool`, ServiceMonitor bearer auth when
`server.api_key` is set, Grafana backend-pool + concurrency panels, doctor Redis
+ `/ready`, hard-reject hermetic burst.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Helm orgPool wiring** — values exist; Deployment never sets env | 3 | 1 | LiteLLM multi-deployment | Point tiers at org GPU pool from one chart toggle | **File** (P2) |
| 2 | **ServiceMonitor scrape auth** — `/metrics` needs Bearer when api_key set | 3 | 2 | Kong / LiteLLM | kube-prometheus scrapes stay green with master key | **File** (P2) |
| 3 | **Grafana backend pool / concurrency** — series exist; dashboard silent | 2 | 1 | LiteLLM | See pool health + in-flight saturation locally | **File** (P3) |
| 4 | **Doctor Redis + /ready** — docs mention; checks missing | 2 | 2 | Portkey health | Catch degraded Redis/pool before kube probes | **File** (P3) |
| 5 | **Hard-reject hermetic burst** — soft-band + TTFT guarded; 402/429 not | 2 | 1 | LiteLLM | Catch reject-path middleware regressions under load | **File** (P3) |
| 6 | **Access-group budgets / MCP introspect / OTLP GenAI** — LiteLLM deltas | 3 | 4 | LiteLLM | Watch until local demand | Watch |
| 7 | **WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

Pruned this run: ServiceMonitor, Grafana TTFT preference, analyst GET config,
ChatGPT Desktop caps docs, TTFT preference hermetic (all shipped morning→afternoon).

---

## Path to enterprise-grade — next 5 milestones

1. **Chart honesty** — orgPool values actually reach the Deployment.
2. **Scrape under lock** — ServiceMonitor bearer when master API key is on.
3. **Operator dashboard parity** — backend pool + concurrency gauges.
4. **Local doctor readiness** — Redis ping and `/ready` before fleet deploys.
5. **Hermetic reject path** — hard 402/429 burst stays ceiling-guarded.

---

## Changelog

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
