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

## Where daari stands (verified in-tree, 2026-09-18)

Soft-budget / observability drain closed: Anthropic SSE L0, Grafana alert + MCP
panels, Helm `metrics_port` + NOTES, MCP Prometheus counters, `agent_turn` on
`daari_meta` (+ OTel), hermetic hard 402, soft USD warn path (header, metrics,
Grafana, doctor, budgets guide), team budget/rate-limit gauges, RFC 7662
introspect, stats `backend_summary` + tier p50/p95, and web-ui pool backends
all shipped. Night-of-17 gap rows 1–8 are gone from the table below.

**Positioning:** LiteLLM still the outward bar (heuristic auto-router, semantic
MCP tool search, Prometheus multiproc / per-key gauges). Portkey / Kong /
OpenRouter quiet on net-new self-host gateway surfaces. Competitive delta moves
to access-group budgets, multiproc metrics process parity, and enterprise
non-goals (WIF / A2A / SOC 2 / admin UI) until local demand appears.

**Inward theme:** Keep the living PRD honest after the soft-budget drain; next
milestones are larger enterprise surfaces, not another panel/doc pass.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Access-group budgets / MCP introspect polish / multiproc / team remaining gauges** | 3 | 3–4 | LiteLLM | Watch until local demand; team gauges + introspect already landed | Watch |
| 2 | **WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

Pruned this run: Anthropic SSE L0, Grafana alert-series panels, Helm
`metrics_port` Service, MCP Prometheus counters, `agent_turn` on `daari_meta`,
Helm NOTES bearer + orgPool, doctor metrics-auth advisory, hermetic hard 402
burst, plus soft USD warn / team gauge / introspect / stats summary follow-ons
from the soft-budget drain.

---

## Path to enterprise-grade — next 5 milestones

1. **Access-group / org budget surfaces** — group-scoped cliffs when local demand appears.
2. **Prometheus multiproc process parity** — LiteLLM-style separate metrics process if scrapes need isolation.
3. **MCP introspect + policy depth** — expand RFC 7662 / tool policy beyond the landed baseline.
4. **Fleet / HA story** — multi-replica readiness without cloud control plane.
5. **Compliance non-goals stay deferred** — WIF / A2A / SOC 2 / admin UI until a paying ask.

---

## Changelog

- **2026-09-18** — Soft-budget / observability drain: pruned shipped gap rows
  1–8 from the 2026-09-17 night table (Anthropic L0 through hermetic 402) and
  soft-USD / team-gauge / introspect / stats-summary follow-ons. Outward bar
  unchanged (LiteLLM). Watch rows only remain; milestones retargeted to larger
  enterprise surfaces.
- **2026-09-17 (night)** — Evening refill drained (stats/web-ui rejects + metrics
  port). Outward: LiteLLM v1.101.0 still the bar (MCP tool metrics, rate-limit
  gauges); Ollama v0.34.2-rc2 llama.cpp-only; Portkey/Kong flat. Inward Anthropic
  stream L0, Grafana alert panels, Helm metrics_port, MCP Prometheus, agent_turn
  meta; filing five issues. Prior P3s (NOTES, doctor metrics-auth, 402 hermetic)
  stay open.
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
- **2026-09-16 (late→08-28)** — Condensed prior drains (fleet auth, soft-warn,
  TTFT, Redis, tenancy, batches, Kong parity, Apache 2.0, this PRD).
