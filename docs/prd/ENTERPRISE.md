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

Night drain closed the evening refill: soft_warnings/rejects on stats + web-ui
and the optional metrics scrape port both merged. Three evening P3s (Helm NOTES,
doctor metrics-auth, hermetic 402 burst) remain open on `main`.

**Positioning:** LiteLLM v1.101.0 still the outward bar (heuristic auto-router,
semantic MCP tool search, separate Prometheus metrics process, MCP tool-call
counters, per-key/team rate-limit gauges). Portkey / Kong / OpenRouter quiet on
net-new self-host gateway surfaces; Ollama at v0.34.2-rc2 (llama.cpp-only).
Competitive delta stays inward: Anthropic stream L0 parity, Grafana panels for
already-emitted alert series, Helm wiring for `metrics_port`, MCP Prometheus
surface, and ADR-0004 `agent_turn` on `daari_meta`.

**Inward theme:** Claude Code stream $0 cache, dashboard lag vs Prometheus,
chart scrape-port wiring, MCP scrape visibility, agent-turn meta honesty.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Anthropic SSE L0 parity** — OpenAI stream hits L0; Anthropic path skips | 4 | 3 | OpenAI path in-tree | Claude Code identical turns stay $0 | **File** (P2) |
| 2 | **Grafana alert-series panels** — retries / false-hits-avoided / budget alerts emit, no panels | 3 | 1 | LiteLLM dashboard | Laptop Grafana sees cliffs without cloud APM | **File** (P2) |
| 3 | **Helm `metrics_port` Service** — app shipped; chart still API-port only | 3 | 2 | LiteLLM metrics port | Private scrapes via chart without Bearer | **File** (P2) |
| 4 | **MCP Prometheus counters** — `/mcp` has policy, no `daari_mcp_*` series | 3 | 2 | LiteLLM MCP tool metrics | Agent tool deny/latency on local scrapes | **File** (P2) |
| 5 | **`agent_turn` on daari_meta** — ADR-0004 checklist still open | 2 | 1 | — | Clients see why L1 skipped without log dive | **File** (P2) |
| 6 | **Helm NOTES bearer + orgPool** | 2 | 1 | Helm ecosystem | Install-time hints | Open (prior) |
| 7 | **Doctor metrics auth advisory** | 2 | 1 | Portkey health | Warn before scrapes go 401 | Open (prior) |
| 8 | **Hermetic hard 402 budget/quota burst** | 2 | 1 | LiteLLM | Catch 402 reject-path regressions | Open (prior) |
| 9 | **Access-group budgets / MCP introspect / multiproc / team remaining gauges** | 3 | 3–4 | LiteLLM | Watch until local demand | Watch |
| 10 | **WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

Pruned this run: stats+web-ui soft/hard rejects, optional metrics scrape port
(app-side) — both shipped evening→night.

---

## Path to enterprise-grade — next 5 milestones

1. **Anthropic stream L0** — Claude Code / Anthropic SSE shares OpenAI-stream cache hits.
2. **Grafana alert panels** — upstream retries, false-hits avoided, budget alerts visible.
3. **Helm scrape-port wiring** — chart exposes `observability.metrics_port` Service/port.
4. **MCP scrape surface** — `daari_mcp_*` counters for ingress tool calls.
5. **agent_turn meta** — ADR-0004 honesty on every response.

---

## Changelog

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
