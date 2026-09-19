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
request-rate KEDA, UTC-day `rpd` (stats, scrape, Grafana, Retry-After),
transcription allowlists, doctor ASR, and transcription chargeback rows
are shipped. Idempotency-Key remains open with an agent already on it and
is not restated below.

**Outward (this run):** LiteLLM stable is still **v1.101.0** (15 Sep).
**v1.102.0** is not stable (rc.1, 13 Sep): auto-router controls, native OCR,
and request/token autoscaling. Portkey **v2.23.0** and Kong **2.0.3** are
unchanged. Ollama **v0.34.2** has no v0.35. OCR, realtime voice, and hosted
shell/Files stay non-goals. No ElevenLabs SDK.

**Inward theme:** chargeback still drops embedding traffic (no key/team on
the row), the Helm chart cannot point a fleet at local ASR, the chargeback
guide never names transcription tiers, and `POST /v1/audio/translations`
is missing while transcriptions exist.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Embedding chargeback** — `POST /v1/embeddings` records `tier=embed` without key or team, so `--key` export drops it | 3 | 2 | LiteLLM (embeddings billed on the same key) | The embedder already runs locally; stamp the key already on the request | File |
| 2 | **Helm ASR URL** — chart sets Redis/Postgres/Prometheus but not `asr.base_url` | 3 | 2 | vLLM / whisper.cpp Helm | One values key keeps audio on the cluster instead of a cloud speech API | File |
| 3 | **Chargeback guide omits audio tiers** — spend CSV has `asr` / `L6` but the guide never says so | 2 | 1 | LiteLLM audio route in spend logs | The row is already on disk; the guide operators follow should name it | File |
| 4 | **Audio translations** — transcriptions exist; `POST /v1/audio/translations` 404s | 3 | 3 | LiteLLM (both audio routes) | Same local ASR process; forward translations, frontier only when enabled | File |
| 5 | **Idempotency-Key / WIF / A2A / SOC 2 / admin UI / OCR** | 2–4 | 2–5 | LiteLLM / cloud | Idempotency is already in progress; the rest stay deferred | Watch |

Pruned this run: day-cap Retry-After, transcription allowlists, doctor ASR,
team and per-key rpd (stats, scrape, Grafana), and transcription chargeback
rows (all shipped).

---

## Path to enterprise-grade — next 5 milestones

1. **Embedding rows on the key** — spend export attributes local embeddings to the virtual key and team.
2. **Helm can point at local ASR** — `asr.baseUrl` becomes `DAARI_ASR__BASE_URL` when set.
3. **Chargeback guide names audio** — `asr` vs `L6`, and denials write no row.
4. **Translations beside transcriptions** — local-first `POST /v1/audio/translations`.
5. **Idempotency** — still in progress; do not refile.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

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
