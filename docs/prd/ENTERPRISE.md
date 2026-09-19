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
request-rate KEDA, and UTC-day `rpd` are shipped. Idempotency-Key remains
open with an agent already on it and is not restated below.

**Outward (this run):** LiteLLM stable is still **v1.101.0** (15 Sep).
**v1.102.0** is not stable (rc.1, 13 Sep): auto-router controls, native OCR,
and request/token autoscaling. Portkey **v2.23.0** (18 Sep) is unchanged
(ElevenLabs speech is cloud-only). Kong AI Gateway **2.0.3** (31 Aug) is
quiet. Ollama **v0.34.2** (15 Sep) is llama.cpp only; no v0.35. vLLM **0.29**
transcriptions are already the local ASR path. OpenRouter hosted shell/Files
stays a non-goal.

**Inward theme:** the day cap and the new audio route are not finished as
operator surfaces. A daily-cap 429 still advertises `Retry-After: 1`.
Transcriptions skip the model allowlist. Doctor never probes ASR. Stats and
per-key scrapes do not show `rpd` remaining (team gauges do).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Daily-cap `Retry-After`** — rpd 429 sets `retry_after` to 1s while `reset_epoch` is the next UTC day | 4 | 1 | Portkey (window reset on daily limits) | The day counter is already local; a true wait stops a retry storm on the on-box pool | File |
| 2 | **Allowlist on transcriptions** — chat/embeddings/Responses 403; `POST /v1/audio/transcriptions` does not | 4 | 2 | LiteLLM (model access on every inference route) | Block a non-allowlisted or frontier ASR upload before the file leaves the machine | File |
| 3 | **Doctor ASR probe** — no check for `asr.base_url` or a fallback with no frontier key | 3 | 2 | vLLM / whisper.cpp health | Catch a dead local ASR process at `daari doctor` instead of the first upload | File |
| 4 | **Team rpd on stats + dashboard** — gauges exist for Prometheus only | 3 | 2 | LiteLLM dashboard | Remaining day cap is already counted locally; the dashboard should show it | File |
| 5 | **Per-key rpd scrape** — team series only; key name, never the secret | 3 | 2 | LiteLLM per-key gauges | Alert on one laptop key without shipping key material to a cloud vendor | File |
| 6 | **Idempotency-Key / WIF / A2A / SOC 2 / admin UI / OCR** | 2–4 | 2–5 | LiteLLM / cloud | Idempotency is already in progress; the rest stay deferred. No ElevenLabs SDK | Watch |

Pruned this run: Responses cancel/delete, local transcriptions, KEDA
request-rate autoscaling, and the rpd cap itself (all shipped). OCR, realtime
voice, and hosted shell/Files stay non-goals.

---

## Path to enterprise-grade — next 5 milestones

1. **Honest daily-cap retry** — `Retry-After` on an rpd 429 waits until the UTC day resets.
2. **Allowlists cover audio** — the same 403 as chat, before any ASR upstream call.
3. **Doctor knows ASR** — warn on an unreachable local base URL or a fallback with no key.
4. **Day cap on the dashboard** — team rpd remaining on `/v1/daari/stats` and the web UI.
5. **Per-key rpd series** — scrape remaining for keys that opted into a day cap.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

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
