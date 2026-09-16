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

**Evening drain shipped** soft-warn Prometheus (#526), report JSON (#527), L1
hermetic ceiling (#528), TTFT-aware routing (#529), doctor soft_ratio=0 (#530)
via PRs #532–#536. Backlog empty mid-session; this refill keeps the loop fed.

**Positioning:** LiteLLM stable **v1.100.1** / **v1.100.0** (2026-09-06) remains
the bar (access-group budgets, custom auto-router tiers, MCP introspection).
Sep-10 harness-aware auto-router posts (Claude Code / Codex envelope strip)
motivate a local parity corpus. Portkey / Kong / OpenRouter flat for this scan.

**Inward theme:** Grafana soft-warn visibility, route dry-run for operators,
TTFT-preference metrics, soft-band hermetic load, harness strip regression tests.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Grafana soft-warn panel** — #526 metrics, no dashboard | 2 | 1 | LiteLLM | Soft-band next to TTFT on local board | **Filed** (P2) |
| 2 | **Route dry-run API/CLI** — LiteLLM `/auto_router/test_routing` parity | 3 | 2 | LiteLLM | Preview L3–L5 without upstream | **Filed** (P2) |
| 3 | **Harness strip corpus** — Claude Code / Codex envelopes | 3 | 2 | LiteLLM | Correct local picks for agent UAs | **Filed** (P2) |
| 4 | **TTFT-preference Prometheus counter** — #529 traces only | 2 | 1 | — | Alert when bias rewrites picks | **Filed** (P3) |
| 5 | **Soft RPM hermetic burst bench** — unit-only today | 2 | 1 | — | Guard soft-header path under load | **Filed** (P3) |
| 6 | **WIF upstream provider auth** | 3 | 3 | Portkey | `secret://oauth` covers most | Watch |
| 7 | **MCP agent identity (SEP-1933)** | 3 | 3 | MCP Tier-1 SDKs | Draft | Watch |
| 8 | **SOC 2 / Gemini facade / A2A / admin UI / images / realtime** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: afternoon refill rows (soft-warn metrics, report JSON, L1
hermetic, TTFT-aware, doctor soft_ratio) — all shipped 2026-09-16 evening.

Open backlog after this run: three P2 + two P3 from the evening refill.

---

## Path to enterprise-grade — next 5 milestones

1. **Soft-warn Grafana** — see soft-band pressure beside hard rejects.
2. **Route dry-run** — operators preview tier picks without Ollama.
3. **Harness strip corpus** — Claude Code / Codex parity for local heuristics.
4. **TTFT-preference metrics** — scrape how often bias fires.
5. **Soft RPM hermetic burst** — load-guard the soft-header path.

---

## Changelog

- **2026-09-16 (evening)** — Drain shipped #526–#530 (PRs #532–#536). Backlog
  empty; refilled five issues (Grafana soft-warn, route dry-run, harness
  corpus, TTFT-preference counter, soft RPM hermetic). Outward: LiteLLM
  harness-aware auto-router (Sep 10) + v1.100.x still stable bar.
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
