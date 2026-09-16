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

## Where daari stands (verified in-tree, 2026-09-16 night)

Fourth prd run today. Route dry-run preview shipped on `main` (squash merge
same evening). Eight fleet/ops issues remain open from evening + late runs.
This night run audited **operator observability and chart hardening**: soft
402/429 warnings are metered (`daari_soft_warnings_total`) but hard rejects
are silent; Redis rate-limit degradation only logs; `/health` and the CLI
expose no package version (upgrade.md already calls this out); Helm still
lacks `securityContext` / PDB / ServiceMonitor; SSO `analyst` exists in
`daari/enterprise/rbac.py` but mutating admin routes and read surfaces are
under-gated.

**Positioning:** LiteLLM **v1.101.0 stable** (09-15; v1.103.0-dev.1 fixes-only
on 09-16). **Ollama v0.34.1 stable** / **v0.34.2-rc0** (llama.cpp bump only).
Portkey gateway OSS last tagged 2026-01; Kong 3.9.3 (06-17); vLLM 0.29.0;
OpenRouter flat. Competitive delta is quiet — inward ops/RBAC wins.

**Inward theme:** hard-reject metrics, version discovery, rate-limit
degradation scrape signal, Helm hardening, SSO RBAC leftovers.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Hard 402/429 Prometheus counters** — soft band metered; cliffs silent | 4 | 1 | LiteLLM / Kong | Alert when local soft warnings become denials | **Filed** (P1) |
| 2 | **CLI `--version` + `/health` version** — upgrade.md documents the hole | 3 | 1 | Every gateway | On-box upgrade/rollback without `pip show` | **Filed** (P2) |
| 3 | **Rate-limit Redis degraded gauge** — log-only today | 3 | 1 | Kong | Page on silent per-pod SQLite fallback | **Filed** (P2) |
| 4 | **Helm securityContext + PDB** — chart has Deploy/Svc/HPA only | 4 | 2 | Kong | Secure defaults + drain floor for local streams | **Filed** (P2) |
| 5 | **SSO RBAC leftovers** — reload-caches ungated; analyst can't read | 4 | 2 | LiteLLM / Portkey | Local SSO without control-plane SaaS | **Filed** (P2) |
| 6 | **Postgres virtual keys/teams** — last per-pod SQLite auth store | 5 | 3 | LiteLLM | On-box resolve, sibling store pattern | Open (P2) |
| 7 | **Helm graceful rollout** — no preStop/termGrace/strategy | 3 | 2 | Kong | Longest requests are local SSE | Open (P2) |
| 8 | **Team RPM/TPM + keys export/import** | 3 | 2 | LiteLLM | Shared GPU ceilings + on-box DR | Open (P2) |
| 9 | **Harness strip corpus / facade capabilities / TTFT+soft benches** | 2–3 | 1–2 | LiteLLM / Ollama | Correct local picks + scrape parity | Open (P2/P3) |
| 10 | **WIF / MCP SEP-1933 / SOC 2 / Gemini / A2A / admin UI** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: route dry-run API/CLI (shipped same evening).

Open backlog after this run: eight prior rows + five night-run rows.

---

## Path to enterprise-grade — next 5 milestones

1. **Fleet-wide auth** — Postgres keys/teams (still the split-brain store).
2. **Operator scrape parity** — hard rejects + rate-limit degradation gauges.
3. **Zero-downtime + hardened chart** — drain lifecycle, securityContext, PDB.
4. **SSO RBAC completeness** — analyst read / admin mutate on every surface.
5. **Version discovery + DR** — `--version`/`/health`, keys export/import.

---

## Changelog

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
- **2026-09-16 (evening)** — Drain shipped; backlog empty; refilled five
  issues (Grafana soft-warn, route dry-run, harness corpus, TTFT-preference
  counter, soft RPM hermetic). Outward: LiteLLM harness-aware auto-router
  noted; v1.100.x still stable bar.
- **2026-09-16 (afternoon)** — Drain shipped; backlog empty; refilled five
  issues (soft-warn Prometheus, report JSON, L1 hermetic ceiling, TTFT-aware
  routing, doctor soft_ratio=0). Outward: LiteLLM harness-/modality
  auto-router posts noted.
- **2026-09-16** — Late-15 leftovers shipped. Backlog empty; refilled five
  issues (stream singleflight, Responses input_tokens, TTFT histogram,
  facade soft quota, doctor multi-replica Redis). Outward: LiteLLM v1.100.1
  noted; v1.101/102 still RC.
- **2026-09-15 (late)** — Same-day fleet sprint closed. Backlog empty
  mid-session; refilled five P2 leftovers. Outward: LiteLLM v1.100.0 noted.
- **2026-09-15** — Fifth same-day drain; never-empty refill + scheduled
  Actions `prd-cycle`.
- **2026-09-14→08-28** (condensed) — Redis resilience, tenancy, batches,
  Kong parity, labeler, Apache 2.0, this PRD.
