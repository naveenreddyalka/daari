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

## Where daari stands (verified in-tree, 2026-09-19)

Fleet/HA, tenancy, governance, Responses cancel/delete, local ASR,
request-rate KEDA, UTC-day `rpd`, transcription allowlists, doctor ASR,
transcription chargeback, embedding chargeback (key and team on the row),
and the chargeback guide's audio tiers are shipped. Idempotency-Key,
Helm `asr.baseUrl`, and `POST /v1/audio/translations` are already queued
and are not restated below.

**Outward (this run):** LiteLLM stable is still **v1.101.0** (15 Sep).
**v1.102.0-rc.2** (16 Sep) only backports Responses request-param leak
fixes. **v1.103.0-dev.2** (18 Sep) is not stable; native OCR and hosted
speech stay non-goals. Portkey enterprise and Kong **2.0.3** (31 Aug)
are unchanged. Ollama **v0.34.2** (15 Sep) has no v0.35. Its documented
batch surface is `POST /api/embed` with an `input` array
([docs](https://docs.ollama.com/api/embed)). No ElevenLabs SDK.

**Inward theme:** embedding and transcription requests record `latency_ms=0`,
so Grafana's latency histogram for those tiers is empty. The Helm chart
can point chat at `orgPool` but the embedder still uses
`ollama.base_url` (`127.0.0.1:11434` inside the pod). Doctor checks that
the embedding model name is in `/api/tags` and never POSTs an embed.
Multipart transcriptions fail JSON parse, so TPM sees 1 token. List
embedding inputs are one HTTP call each.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Embed/ASR latency is zero** — `compute_embeddings` and transcriptions call `metrics.record` with `latency_ms=0`, so `daari_request_latency_ms` for `embed` / `asr` never fills | 3 | 1 | LiteLLM (per-route latency) | Local embed and ASR only win if operators can see they are fast | File |
| 2 | **Helm Ollama URL** — chart sets `orgPool` for chat routing but never `DAARI_OLLAMA__BASE_URL`; embeddings and L3 stay on localhost | 4 | 2 | vLLM / Ollama Helm (`OLLAMA_HOST`) | One values key keeps the embedder on the same GPU pool as chat | File |
| 3 | **Doctor embedding probe** — L1 check stops at model name in `/api/tags`; a 500 from `/api/embed` is invisible until a request | 3 | 2 | Ollama health + LiteLLM model health | Fail at `daari doctor`, not on the first RAG call | File |
| 4 | **Audio TPM** — multipart `POST /v1/audio/transcriptions` is not JSON, so `estimate_request_tokens` returns 1 | 3 | 2 | LiteLLM (audio counts toward limits) | Local ASR still burns GPU; TPM should see bytes, not a chat-shaped body | File |
| 5 | **Serial embedding HTTP** — list inputs miss cache one `POST /api/embeddings` at a time; Ollama `/api/embed` accepts an array | 3 | 3 | Ollama batch embed; LiteLLM batch embeddings | One local call per batch, no hosted embedding API | File |
| 6 | **Idempotency / translations / Helm ASR / WIF / A2A / SOC 2 / admin UI / OCR** | 2–4 | 2–5 | LiteLLM / cloud | First three are already queued; the rest stay deferred | Watch |

Pruned this run: embedding chargeback rows and the chargeback guide's
audio-tier sentence (both shipped).

---

## Path to enterprise-grade — next 5 milestones

1. **Time embed and ASR** — stats and Prometheus latency histograms show wall time, not zero.
2. **Helm can point the embedder at the pool** — `ollama.baseUrl` becomes `DAARI_OLLAMA__BASE_URL` when set.
3. **Doctor probes embeddings** — L1 on and the model listed, but `/api/embed` down, fails the check.
4. **Transcription bytes count toward TPM** — a multi-kilobyte upload is not 1 token.
5. **Batch list embeds** — cache misses in one `POST /v1/embeddings` share one Ollama call.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR) stay deferred until a paying ask.

---

## Changelog

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
