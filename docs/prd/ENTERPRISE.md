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

## Where daari stands (verified in-tree, 2026-09-14)

**Fourth consecutive same-day drain.** The 09-13 refill #452–#456 all merged the
same evening (PRs #458–#462): batch/file/response tenancy scoping,
Anthropic-native `/v1/models`, `anthropic-beta` passthrough, and files
retention. Backlog and open PRs were both empty at run start.

**Positioning:** outward is flat — LiteLLM stable is still v1.100.1 (newest tag
v1.102.0-rc.1, scanned 09-13), Portkey v2.22.0, Kong 2.0.3, Ollama 0.34.0,
vLLM 0.29.0, and SEP-1933 still draft. Two ecosystem signals matter:
**OpenRouter launched US in-region routing 09-09** (`us.openrouter.ai` /
`eu.openrouter.ai`, Business/Enterprise-gated — a data-residency story daari
can beat local-first), and TrueFoundry entered the auto-routing fight 09-09
claiming latency superiority over LiteLLM.

**Inward theme of this run: dependency-failure resilience and metering.**
With `cache.backend: redis` (the documented fleet setup) and any RPM/TPM limit,
the rate-limit middleware calls Redis with no error handling and no socket
timeout anywhere in the tree — a Redis outage 500s every request; a hung Redis
blocks them indefinitely (LiteLLM hardened this exact path in v1.102-rc.1).
Also verified: `keys create`/`revoke` and invalid-key 401s are unaudited (only
`keys.rotate` and `auth.key_expired` are); batches/files break in the default
`replicaCount: 2` Helm deploy (documented caveat); and USD budgets cannot meter
$0 local tiers — no request-count quotas exist.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Redis outage takes down the gateway** — unguarded `RedisCounterBackend.increment()` in the rate-limit middleware; no `socket_timeout` on any Redis client; `/ready` never probes Redis | 5 | 2 | LiteLLM v1.102-rc.1 ([PR 40624](https://github.com/BerriAI/litellm/pull/40624), chaos test [PR 40482](https://github.com/BerriAI/litellm/pull/40482)) | SQLite counter backend already exists — degrade to per-replica enforcement, never 500 | **Filed [#463](https://github.com/naveenreddyalka/daari/issues/463)** (P1) |
| 2 | **Audit holes where SOC 2 looks first** — `keys create`/`revoke`, team ops, invalid-key 401s, and cross-tenant artifact denials all unaudited | 4 | 2 | LiteLLM / Portkey admin trails | Hash-chained local SQLite (#378) verifiable offline; just needs coverage | **Filed [#464](https://github.com/naveenreddyalka/daari/issues/464)** (P2) |
| 3 | **Batches/Files break at `replicaCount: 2`** — per-pod SQLite/disk; GET can hit a replica that never saw the job | 4 | 3 | LiteLLM (DB-backed everything) | Ledger already proves the pattern: SQLite default, opt-in shared Postgres (`daari[postgres]`) | **Filed [#465](https://github.com/naveenreddyalka/daari/issues/465)** (P2) |
| 4 | **No data-residency pin on L6** — OpenRouter in-region routing (09-09) is enterprise-gated; daari has `zdr` per slot but no `region` | 3 | 2 | OpenRouter ([announcement](https://openrouter.ai/blog/announcements/us-in-region-routing/)) | L0–L5 never leave the operator's hardware; only the L6 remainder needs pinning | **Filed [#466](https://github.com/naveenreddyalka/daari/issues/466)** (P2) |
| 5 | **USD budgets can't meter $0 local tiers** — no request-count quotas over long windows; one key can monopolize shared GPU all month | 3 | 2 | Portkey usage limits / LiteLLM key limits | Request counts are the natural unit for rationing local GPU; multi-window budget machinery exists | **Filed [#467](https://github.com/naveenreddyalka/daari/issues/467)** (P2) |
| 6 | **Percentile-TTFT routing** — LiteLLM still rc-only | 2 | 3 | LiteLLM `-rc` | Need latency histograms first | Watch |
| 7 | **MCP agent identity** — SEP-1933 draft (upd 09-07); Skills 2640 / audit-context 2817 / server-cards 2127 active | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` ready | Watch |
| 8 | **Session-cumulative savings surfacing** — LiteLLM rc shows session savings inside Claude Code/Codex | 2 | 2 | LiteLLM rc | `x-daari-response-cost-avoided` shipped; rollup needs affinity store | Watch (stable release or client ask) |
| 9 | **SOC 2 / Gemini facade / A2A / admin UI / off-peak / `/v1/images` / realtime / WIF / streamed `usage.cost`** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: #452–#456 rows (all shipped 09-13, PRs #458–#462).

Open backlog after this run:
[#463](https://github.com/naveenreddyalka/daari/issues/463) (P1),
[#464](https://github.com/naveenreddyalka/daari/issues/464)–[#467](https://github.com/naveenreddyalka/daari/issues/467) (P2).

---

## Path to enterprise-grade — next 5 milestones

1. **Survive dependency failure** ([#463](https://github.com/naveenreddyalka/daari/issues/463)) — a router that 500s when Redis blips is not an HA story; fail open to local enforcement, bound every Redis call, surface it on `/ready`.
2. **Complete the audit trail** ([#464](https://github.com/naveenreddyalka/daari/issues/464)) — the hash chain is only as good as its coverage; key lifecycle, failed auth, and tenancy denials are the events reviewers ask for.
3. **Make the fleet deploy honest** ([#465](https://github.com/naveenreddyalka/daari/issues/465)) — Batches/Files must work at the Helm chart's own default replica count.
4. **Own the residency narrative** ([#466](https://github.com/naveenreddyalka/daari/issues/466)) — "90% of traffic never leaves your rack, and the remainder is region-pinned" beats every cloud gateway's compliance page.
5. **Meter what local actually costs** ([#467](https://github.com/naveenreddyalka/daari/issues/467)) — request-count quotas ration shared GPU capacity that USD budgets can't see.

---

## Changelog

- **2026-09-14** — Fourth same-day drain: #452–#456 merged 09-13 evening
  (PRs #458–#462); backlog empty. Outward flat (LiteLLM v1.100.1 stable /
  v1.102.0-rc.1, Portkey v2.22.0, Kong 2.0.3, Ollama 0.34.0, vLLM 0.29.0,
  SEP-1933 draft); new signals: OpenRouter US in-region routing (09-09),
  TrueFoundry auto-routing entry. Inward: Redis outage 500s the rate-limit
  middleware (no error handling, no socket timeouts anywhere); keys
  create/revoke + invalid-key 401s + tenancy denials unaudited; batches/files
  broken at default Helm replicas; no request-count quotas. Filed
  [#463](https://github.com/naveenreddyalka/daari/issues/463) (P1),
  [#464](https://github.com/naveenreddyalka/daari/issues/464)–[#467](https://github.com/naveenreddyalka/daari/issues/467)
  (P2).
- **2026-09-13** — Stored-artifact tenancy audit (batch/file/response reads
  unscoped) + Portkey v2.22 parity (Anthropic `/v1/models`, `anthropic-beta`)
  + files retention. Filed #452–#456; all shipped same day. Fixed a CI date
  bomb in the audit-export test in the same PR.
- **2026-09-12** — Batch slice audit (governance bypass, `/v1/files`,
  durability, idle-yield) + `daari configure`. Filed #441–#445; all shipped
  same day.
- **2026-09-11 / late / pm** — Filed #418–#422 (harness-aware headline) and
  #430–#434 (Kong parity + Batch API); pm run no-delta.
- **2026-09-10** — Filed #409–#412; `AUTODEV_GH_TOKEN` set.
- **2026-09-09→08-28** (condensed) — #374–#401 refills, park era, labeler,
  Apache 2.0, this PRD.
