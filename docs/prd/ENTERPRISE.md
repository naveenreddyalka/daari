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

## Where daari stands (verified in-tree, 2026-09-16)

**Afternoon drain shipped** L1 singleflight, RPM soft warn, TTFT Grafana panel,
report request-quotas, L0 singleflight hermetic ceiling (PRs #521–#525). Mid-
session backlog empty again; this refill keeps the loop fed.

**Positioning:** LiteLLM stable **v1.100.1** (2026-09-10) remains the bar
(access-group budgets, custom auto-router tiers, MCP introspection). Auto-router
posts cover harness-aware classification and modality/context routing. Portkey /
Kong / OpenRouter flat for this scan.

**Inward theme:** soft-band observability (Prometheus + doctor), FinOps JSON
CLI, L1 stampede hermetic guard, then opt-in TTFT-aware local tier preference.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Soft-warn Prometheus counters** — headers only, no scrape signal | 2 | 1 | LiteLLM | Alert before hard 402/429 on local fleet | **Filed** (P2) |
| 2 | **`daari report --format json`** — CLI still text/md only | 2 | 1 | — | FinOps scrapers without curl shape | **Filed** (P2) |
| 3 | **L1 singleflight hermetic ceiling** — #520 covered L0 only | 2 | 1 | — | Guard embed stampede regressions | **Filed** (P2) |
| 4 | **Percentile-TTFT local tier preference** — histograms exist, unused | 3 | 3 | LiteLLM | Prefer snappy warm local tier | **Filed** (P3) |
| 5 | **Doctor quiet when soft_budget_ratio=0** with quotas/RPM | 2 | 1 | — | Catch disabled soft band early | **Filed** (P3) |
| 6 | **WIF upstream provider auth** | 3 | 3 | Portkey | `secret://oauth` covers most | Watch |
| 7 | **MCP agent identity (SEP-1933)** | 3 | 3 | MCP Tier-1 SDKs | Draft | Watch |
| 8 | **SOC 2 / Gemini facade / A2A / admin UI / images / realtime** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: prior refill rows (stream L0 SF, Responses input_tokens, TTFT
histogram, facade soft quota, doctor fleet Redis) — all shipped 2026-09-16.

Open backlog after this run: three P2 + two P3 from the afternoon refill.

---

## Path to enterprise-grade — next 5 milestones

1. **Soft-warn metrics** — alert when agents hover in soft band.
2. **JSON report CLI** — FinOps without HTTP shape gymnastics.
3. **L1 stampede hermetic guard** — protect local GPU under fan-out.
4. **TTFT-aware local preference** — use histograms for snappy tiers.
5. **Honest soft-band doctor** — ratio=0 with caps is a loud warn.

---

## Changelog

- **2026-09-16 (afternoon)** — Drain shipped #516–#520 (PRs #521–#525). Backlog
  empty; refilled five issues (soft-warn Prometheus, report JSON, L1 hermetic
  ceiling, TTFT-aware routing, doctor soft_ratio=0). Outward: LiteLLM harness-
  aware / modality auto-router posts noted; v1.100.1 still stable bar.
- **2026-09-16** — Late-15 leftovers shipped (PRs #501–#505). Backlog empty;
  refilled five issues (stream singleflight, Responses input_tokens, TTFT
  histogram, facade soft quota, doctor multi-replica Redis). Outward: LiteLLM
  v1.100.1 noted; v1.101/102 still RC. Portkey/Kong/OpenRouter flat.
- **2026-09-15 (late)** — Same-day fleet sprint closed (#481–#485 → PRs
  #490–#494; #476–#478 earlier). Backlog empty mid-session; refilled five P2
  leftovers (profile pins, doctor audit/webhook warnings, Responses
  retention, request-quota soft band, L0 singleflight). Outward: LiteLLM
  v1.100.0 (access-group budgets, custom router tiers) noted; v1.101 bar
  unchanged. Portkey/Kong/OpenRouter/Ollama flat.
- **2026-09-15** — Fifth same-day drain: #463–#467 merged overnight (PRs
  #469–#473). Never-empty refill + scheduled Actions `prd-cycle` (PR #479)
  and session cost rollup (PR #480). Filed #481–#485 (fleet half-finished).
- **2026-09-14** — Redis resilience audit; filed #463–#467; all shipped
  overnight.
- **2026-09-13→08-28** (condensed) — tenancy, batches, Kong parity, labeler,
  Apache 2.0, this PRD.
