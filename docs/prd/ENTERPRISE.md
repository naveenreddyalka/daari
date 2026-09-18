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

## Where daari stands (verified in-tree, 2026-09-18 late)

Fleet/HA, tenancy, and the soft-budget / observability drain are closed.
The evening governance set (model allowlists, chargeback rows, config
validate, master-key overlap, per-provider retry) is already on the backlog
and is not restated below.

**Outward (this run):** LiteLLM **v1.101.0** (15 Sep) is still the stable bar
(heuristic auto-router, semantic MCP tool search, off-peak pricing, separate
metrics port). **v1.102.0-rc.1 / rc.2** is not stable: auto-router controls,
native OCR, request/token autoscaling, and stricter Responses-ID auth for
retrieve / cancel / delete. Portkey **v2.23.0** (18 Sep) adds ElevenLabs
speech endpoints and a streaming-usage default — provider breadth, not a new
gateway core (daari already honors `include_usage`). Kong AI Gateway **2.0.3**
(31 Aug) is quiet. Ollama **v0.34.2** (15 Sep) is first-run setup + llama.cpp;
tool search and response compaction from v0.34.0 are already in the facade.
vLLM **0.29** (9 Sep) exposes `/v1/audio/transcriptions`. OpenRouter's hosted
shell/Files API is a cloud sandbox — non-goal.

**Inward theme:** gateway lifecycle and spend safety. Stored Responses can be
fetched but not cancelled or deleted. No `Idempotency-Key`. No audio
transcription route (do not add an ElevenLabs dependency; local ASR or 501).
Helm HPA scales on CPU only. Rate limits are a 60-second rpm/tpm window.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Responses cancel + delete** — `GET /v1/responses/{id}` and background jobs exist; no cancel or delete on SQLite or Postgres | 4 | 2 | LiteLLM 1.102 RC (ID auth on cancel/delete) | The store is on the operator's disk; cancel stops a runaway local-or-frontier job without a cloud control plane | File |
| 2 | **`Idempotency-Key` on chat + Responses** — retries re-route and can double-charge L6 | 4 | 2 | OpenAI / Portkey | Replay the stored result (often a local tier) instead of paying frontier twice | File |
| 3 | **`POST /v1/audio/transcriptions`** — no `/v1/audio` route; vLLM 0.29 and LiteLLM expose it. Portkey v2.23's ElevenLabs path is cloud-only | 4 | 3 | vLLM, LiteLLM | Audio stays on the box when a local ASR backend is configured; 501 rather than a silent cloud upload | File |
| 4 | **Request-rate autoscaling** — Helm HPA is CPU-only; `daari_requests_total` is already exported | 3 | 2 | LiteLLM 1.102 RC | Cache-heavy router traffic is not CPU-bound; scale on the counter daari already owns | File |
| 5 | **Daily request cap (rpd)** beside rpm/tpm — `WINDOW_SECONDS` is hard-coded to 60 | 3 | 2 | Portkey (rpd / weekly windows) | A local gateway can enforce a calendar-day cap without a cloud quota service | File |
| 6 | **Access-group budgets / multiproc metrics / WIF / A2A / SOC 2 / admin UI** | 2–3 | 3–5 | LiteLLM / Kong / cloud | Watch until local demand; allowlists and team budgets already exist or are queued | Watch |

Pruned this run: evening rows 1–5 (already queued) and the evening audio watch
row (promoted to row 3 as local-first transcription, not a new speech vendor).
OCR, realtime voice, and hosted shell/Files stay non-goals (new runtime deps
or a cloud sandbox).

---

## Path to enterprise-grade — next 5 milestones

1. **Responses lifecycle** — cancel in-flight background jobs and delete stored objects under the same tenancy as GET.
2. **Idempotent writes** — one `Idempotency-Key` replays chat and Responses without a second route.
3. **Local-first audio** — OpenAI transcriptions shape, local ASR first, no new runtime dependency.
4. **Scale on requests, not CPU** — optional chart autoscaling from `daari_requests_total` (off by default).
5. **Day-scoped abuse caps** — rpd next to rpm/tpm so a key cannot run the minute window all day.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

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
