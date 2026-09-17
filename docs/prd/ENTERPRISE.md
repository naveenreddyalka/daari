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

Morning drain closed the night ops/RBAC backlog: SSO analyst-read / admin-mutate
(#555), TTFT preference counter (#539), soft RPM hermetic burst (#540), and
Ollama facade capabilities (#547) all merged. Prior fleet rows (Postgres keys,
Helm graceful + securityContext/PDB, team RPM, keys DR, hard-reject metrics,
version exposure, Redis degraded gauge) already on `main`.

**Positioning:** LiteLLM **v1.100.1** stable bar (v1.100.0 access-group budgets /
custom auto-router tiers, 09-06). Ollama capability reporting already matched
in-tree via facade (#547). Portkey OSS / Kong / OpenRouter quiet. Competitive
delta stays inward: scrape/chart parity and SSO read surfaces.

**Inward theme:** Helm ServiceMonitor, Grafana for TTFT preference, analyst
config GET, ChatGPT Desktop capability docs, TTFT preference hermetic bench.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Helm ServiceMonitor** — chart still Deploy/Svc/HPA/PDB only | 3 | 2 | Kong / kube-prometheus | Scrape `/metrics` without hand-rolled ServiceMonitor | **Filed** (P2) |
| 2 | **Grafana TTFT preference panel** — counter shipped; dashboard silent | 2 | 1 | LiteLLM | See L4→L3 bias without PromQL | **Filed** (P3) |
| 3 | **Analyst GET config** — mutate gated; config GET still admin-only | 3 | 1 | Portkey | FinOps read of live routing without admin | **Filed** (P3) |
| 4 | **ChatGPT Desktop capability docs** — facade advertises; recipe silent | 2 | 1 | Ollama clients | Capability-aware Desktop keeps tools UI | **Filed** (P3) |
| 5 | **TTFT preference hermetic bench** — unit counter only; no wall ceiling | 2 | 1 | LiteLLM | Catch preference-path regressions under burst | **Filed** (P3) |
| 6 | **Access-group budgets / MCP introspect** — LiteLLM 1.100 deltas | 3 | 4 | LiteLLM | Watch until local demand | Watch |
| 7 | **WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

Pruned this run: SSO RBAC leftovers, facade capabilities, TTFT preference
counter, soft RPM hermetic, Helm securityContext/PDB, Postgres keys, team RPM,
keys export, graceful rollout, hard rejects, version exposure, Redis degraded
gauge (all shipped).

---

## Path to enterprise-grade — next 5 milestones

1. **Prometheus Operator scrape** — optional Helm ServiceMonitor.
2. **Operator dashboard parity** — TTFT preference + remaining scrape series.
3. **SSO read completeness** — analyst GET config / FinOps surfaces.
4. **Client recipe honesty** — Desktop/JetBrains capability notes stay current.
5. **Hermetic benches** — preference + soft-band paths stay ceiling-guarded.

---

## Changelog

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
