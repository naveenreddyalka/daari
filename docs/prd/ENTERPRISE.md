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

## Where daari stands (verified in-tree, 2026-09-16 late)

Three prd runs today; the evening refill's Grafana soft-warn row shipped within
minutes (PR merged 14:35). Four evening issues remain open. This late run
audited the **fleet auth story**: `postgres.enabled=true` flips five stores to
Postgres, but virtual keys/teams stay per-pod SQLite (`daari/auth/virtual_keys.py`)
— SSO-minted keys 401 on sibling replicas, revocation doesn't propagate, and
neither doctor's `sqlite_artifacts` nor the chart's fleet-sqlite-warning
annotation mention the keys store. Helm also has no preStop/termination-grace/
rolling strategy; teams have budgets but no aggregate RPM/TPM; the Ollama
facade hardcodes `capabilities: ["completion"]`; keys/teams have no
export/import (backup/DR).

**Positioning:** LiteLLM **v1.101.0 stable** (09-15; v1.103.0-dev.1 on 09-16 is
fixes only). **Ollama v0.34.1 stable** (09-14): consistent capability reporting
on `/api/tags` — clients gate tools/thinking on it, so the facade must
advertise real capabilities. Portkey v2.22.0 / Kong 2.0.3 / OpenRouter (08-19)
/ vLLM 0.29.0 unchanged.

**Inward theme:** fleet-wide auth (Postgres keys), rollout safety, team quotas,
facade capability parity, auth-store backup/DR.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Postgres virtual keys/teams** — last per-pod SQLite store; SSO mints 401 across replicas | 5 | 3 | LiteLLM | On-box resolve, psycopg pattern in 5 sibling stores, zero new deps | **Filed** (P2) |
| 2 | **Helm graceful rollout** — no preStop/termGrace/strategy; SSE cut on upgrade | 3 | 2 | Kong | Local streams are the longest requests; batch resume already restart-safe | **Filed** (P2) |
| 3 | **Team-level RPM/TPM** — teams have budgets only; N keys = N× per-key RPM | 3 | 2 | LiteLLM | Team ceilings map to shared on-box GPU capacity | **Filed** (P2) |
| 4 | **Keys/teams export/import** — no backup/DR for the auth store | 3 | 2 | LiteLLM (control plane) | On-box state needs portable export; hashes only | **Filed** (P2) |
| 5 | **Facade capabilities parity** — Ollama 0.34.1 clients gate tools on capability lists | 2 | 2 | Ollama | Router handles tools; facade under-advertises | **Filed** (P3) |
| 6 | **Route dry-run API/CLI** — LiteLLM `/auto_router/test_routing` parity | 3 | 2 | LiteLLM | Preview L3–L5 without upstream | Open (P2) |
| 7 | **Harness strip corpus** — Claude Code / Codex envelopes | 3 | 2 | LiteLLM | Correct local picks for agent UAs | Open (P2) |
| 8 | **TTFT-preference counter / soft RPM hermetic bench** | 2 | 1 | — | Observability for the new soft-band paths | Open (P3) |
| 9 | **WIF upstream provider auth** | 3 | 3 | Portkey | `secret://oauth` covers most | Watch |
| 10 | **MCP agent identity (SEP-1933)** | 3 | 3 | MCP Tier-1 SDKs | Draft | Watch |
| 11 | **SOC 2 / Gemini facade / A2A / admin UI / images / realtime** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: Grafana soft-warn panel (shipped 2026-09-16 14:35).

Open backlog after this run: four evening rows + five late-run rows.

---

## Path to enterprise-grade — next 5 milestones

1. **Fleet-wide auth** — Postgres keys/teams; the last split-brain store.
2. **Zero-downtime rollouts** — Helm drain lifecycle for long local streams.
3. **Team quotas** — aggregate RPM/TPM mapping to shared GPU capacity.
4. **Auth backup/DR** — versioned keys/teams export/import, hashes only.
5. **Operator preview + parity** — route dry-run, harness corpus, facade
   capabilities.

---

## Changelog

- **2026-09-16 (late)** — Delta scan: LiteLLM v1.103.0-dev.1 fixes-only;
  Ollama v0.34.1 stable (capability reporting, faster `/api/tags`); rest flat.
  Inward fleet-auth audit; filed five issues (Postgres keys/teams, Helm
  graceful rollout, team RPM/TPM, keys export/import, facade capabilities).
  Pruned shipped Grafana soft-warn row.
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
