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

## Where daari stands (verified in-tree, 2026-09-19 evening)

Fleet/HA, tenancy, governance, Responses cancel/delete, local ASR,
request-rate KEDA, UTC-day `rpd`, transcription allowlists, doctor ASR,
and transcription/embedding chargeback are shipped. Already queued and
not restated below: Idempotency-Key, Helm `asr.baseUrl`, audio
translations, embed/ASR latency, Helm Ollama URL, doctor embed probe,
audio TPM, and batched list embeds.

**Outward (this run, delta on the 16:55 scan):** LiteLLM stable is still
**v1.101.0**; v1.103.0-dev.2 (18 Sep) is not stable. Portkey enterprise
and Kong **2.0.3** unchanged. **Ollama v0.34.3-rc1** (19 Sep) adds a
`thinking` controls object (`values` + `default`) to `GET /api/show` —
facade parity becomes a fileable row when it goes stable (same pattern
as the 0.34.1 `capabilities` field). llama.cpp nightlies only; vLLM
0.29.0 flat.

**Inward theme: cache tenancy and request lifecycle.** `cache_key()`
(`daari/cache/exact.py`) hashes messages, model, sampling — never
`key_id`/`team_id` (`RequestMeta` carries both, comment says "Not part
of the cache key"). The Redis L0 prefix is the global `daari:l0:`, and
the L1 nearest scan matches on model|temperature|tools only, so a
semantic hit can serve one team's stored completion to another team.
No `request.is_disconnected()` anywhere: an abandoned non-streaming
request keeps the local GPU or frontier call running to completion.
Cache ops are blunt: `daari context clear` is rmtree-everything, Redis
L0 `prune()` is a no-op, and there is no invalidate-by-model/key/entry.
Timeouts are fixed per tier (`local_timeout_seconds` 120 + 90 per
frontier leg on escalation) with no request-scoped deadline. The
request log stores metadata only (no prompt bodies — verified) but is
absent from `RetentionSettings.prune_all`, so it only rotates by size.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Cache is tenant-blind** — L0/L1 keys have no `key_id`/`team_id` dimension; semantic hits cross team boundaries; no per-key/team cache scope flag | 5 | 2 | Portkey (workspace-scoped cache); LiteLLM cache-key metadata | Shared org cache stays the default win; a `cache_scope` of team/key makes it safe for confidential teams without a hosted cache | File |
| 2 | **Abandoned requests burn GPU** — no disconnect detection; non-stream upstream calls run to completion after the client hangs up; no cancelled-request metric | 4 | 3 | Kong/Envoy (proxy abort propagates upstream) | Cancelled local inference frees the GPU for the next request — the scarce resource IS local | File |
| 3 | **No selective cache invalidation** — only rmtree-all `context clear` + TTL prune (Redis prune is a no-op); nothing by model, key, team, or entry hash | 3 | 2 | LiteLLM (cache delete/flush admin endpoints); GPTCache | A bad cached answer is purged in one admin call instead of nuking the whole org cache | File |
| 4 | **No end-to-end deadline** — each tier restarts a full fixed timeout on escalation (120s local + 90s per frontier leg worst-case); `latency_budget_ms` only picks the first tier | 4 | 3 | LiteLLM (`request_timeout`); Kong route timeouts | Escalation chains are daari's core mechanic; a wall-clock budget makes p99 provable to SRE | File |
| 5 | **Request log outside retention** — `cursor-requests.log` rotates by size only; not in `RetentionSettings`/`prune_all`; no time-based purge for compliance | 2 | 1 | Cloud gateways (retention policies) | One retention sweep already prunes traces/ledger/audit — logs should follow | File |
| 6 | **Ollama 0.34.3 `/api/show` thinking controls / idempotency / translations / Helm ASR / embed-ASR set / WIF / A2A / SOC 2 / admin UI / OCR** | 2–4 | 2–5 | Ollama / LiteLLM / cloud | First is rc-gated; next eight are queued; the rest stay deferred | Watch |

Pruned this run: the embed/ASR measurement rows (all five filed as issues
by the 16:55 sibling run and now queued).

---

## Path to enterprise-grade — next 5 milestones

1. **Tenant-scoped caching** — optional `cache_scope: team|key` on virtual keys/teams folds `key_id`/`team_id` into L0/L1 keys and the Redis prefix.
2. **Cancel on disconnect** — `is_disconnected()` polling + upstream task cancel; a `daari_cancelled_requests` counter proves freed GPU time.
3. **Cache invalidation surface** — admin route + CLI to purge by model, key/team, or entry hash, Redis-aware.
4. **Request deadline** — `X-Daari-Deadline-Ms` propagates remaining wall-clock into every tier's httpx timeout and stops escalation when spent.
5. **Log retention parity** — the gateway request log joins the retention sweep.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR) stay deferred until a paying ask.

---

## Changelog

- **2026-09-19 (cache tenancy)** — Delta run an hour after the 16:55
  sibling (embed/ASR set queued). Outward delta: Ollama v0.34.3-rc1 adds
  `/api/show` thinking controls (watch until stable); LiteLLM/Portkey/
  Kong/vLLM flat. Inward theme verified in-tree: tenant-blind L0/L1
  cache keys, no disconnect cancellation, no selective cache
  invalidation, no request-scoped deadline, request log outside the
  retention sweep. Filing all five.

- **2026-09-19 (embed drain)** — Embedding chargeback and the chargeback
  guide's audio sentence shipped. Outward: LiteLLM stable still v1.101.0;
  v1.102.0-rc.2 is a Responses leak backport; v1.103.0-dev.2 is not stable.
  Portkey and Kong 2.0.3 flat. Ollama v0.34.2, no v0.35; `/api/embed` batch
  is the local surface. Filing embed/ASR latency, Helm Ollama URL, doctor
  embed probe, audio TPM, and batched embeds. Idempotency, Helm ASR, and
  audio translations left queued.
- **2026-09-19 (refill)** — Day-cap surfaces, transcription allowlists, doctor
  ASR, and transcription chargeback shipped. Outward still flat: LiteLLM
  v1.101.0 stable, v1.102.0 rc.1, Portkey v2.23.0, Kong 2.0.3, Ollama
  v0.34.2. Filing embedding chargeback, Helm ASR URL, chargeback docs, and
  audio translations. Idempotency left in progress.
- **2026-09-19** — Prior lifecycle/audio/KEDA/rpd rows shipped. Outward flat:
  LiteLLM v1.101.0 stable (v1.102.0 still RC), Portkey v2.23.0, Kong 2.0.3,
  Ollama v0.34.2, no v0.35. Inward: day-cap retry, transcription allowlists,
  doctor ASR, stats/dashboard rpd, per-key rpd scrape. Idempotency left in
  progress, not refiled.
- **2026-09-18 (late)** — Evening governance/chargeback set already queued, so
  this run moved on. Outward: LiteLLM v1.101.0 stable; v1.102.0 still RC
  (Responses cancel/delete auth, request-rate autoscale). Portkey v2.23.0
  ElevenLabs is cloud speech, not a reason to add a vendor SDK. Kong 2.0.3
  flat. Ollama v0.34.2 setup/llama.cpp only. vLLM 0.29 transcriptions is the
  local-first surface. Filing five issues (Responses lifecycle, idempotency,
  audio route, request-rate HPA, rpd).
- **2026-09-18 (evening)** — All 19 fleet/tenancy/resilience issues from the
  09-14→09-16 runs confirmed shipped; backlog had degraded to P3 docs/test
  trivia. Rebuilt table around governance + chargeback: filing five issues
  (model allowlists, spend export, config validate, master key rotation,
  per-provider retry/timeout). Outward: Portkey v2.23.0, Ollama v0.34.2
  stable, LiteLLM bar unchanged at v1.101.0, Kong/OpenRouter/vLLM flat.
- **2026-09-18 (early)** — Soft-budget / observability drain: pruned shipped gap
  rows from the 2026-09-17 night table. Watch rows only remained.
- **2026-09-17 (4 runs)** — Morning→night refills drained same-day: ops/RBAC,
  facade/bench, stats/web-ui, scrape port, Anthropic SSE L0, Grafana alert + MCP
  panels, Helm metrics port, agent_turn meta, soft USD warn, team gauges,
  introspect, hermetic 402. Outward flat (LiteLLM v1.101.0 bar).
- **2026-09-16 (3 runs)** — Fleet-auth theme: Postgres keys/teams, Helm graceful
  rollout, team RPM/TPM, keys export/import, facade capabilities; plus dry-run,
  TTFT counter, bench + harness rows. Ollama v0.34.1 stable.
- **2026-09-15 and earlier** — Condensed: loop restructure (never-empty refill +
  14:00 UTC Actions prd run), fleet story, resilience + metering, stored-artifact
  tenancy, Batch/Files API, pricing refresh, session affinity, stall escalation,
  MCP pagination, Apache 2.0 relicense, this PRD's creation (2026-08-28).
