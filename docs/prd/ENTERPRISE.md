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

## Where daari stands (verified in-tree, 2026-09-21)

Shipped since the 2026-09-20 resilience scan: local TTS (`POST /v1/audio/speech`)
plus Helm `tts.baseUrl` / `tts.model` / `tts.voice`, opt-in
`routing.local_pool.frontier_fallback`, OTLP logs (`observability.otlp_logs`),
doctor probes for deadline, TTS, OTLP logs, local-pool failover, and
`scoped_cache_fleet`. Still queued on open PRs (not refiled): L1 entries
namespaced by embedding model, `daari models warm`, virtual-key `--priority`,
and the P3 docs/test tail. Idempotency-Key remains in progress.

**Outward (this run):** GitHub latest non-prerelease tags — LiteLLM **v1.101.0**
(2026-09-15), Ollama **v0.34.2** (2026-09-15), vLLM **v0.29.0** (2026-09-09).
No newer stable bar than the prior scan. Portkey enterprise and Kong AI Gateway
unchanged at the versions already recorded. Ollama `typical_p` deprecation is
create-time only; existing GGUF models keep it, so daari does not need a
sampler change this run.

**Inward theme: speech chart parity and cancel-phase docs.** Helm pins
`tts.model` but not `asr.model`, even though `AsrSettings.model` already
replaces the client model for transcriptions and translations. Helm also
omits `asr.frontier_fallback`, so a chart deploy cannot opt into the governed
cloud transcription path the doctor already warns about. Prometheus docs list
cancel phases through `tts` and skip `mcp`, which the gateway already records.
The ASR guide never names Helm `asr.baseUrl`.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Helm has no `asr.model`** — `AsrSettings.model` pins the on-box whisper id; the chart only mounts `asr.baseUrl` while `tts.model` already ships | 3 | 1 | LiteLLM helm model aliases | Fleet whisper stays local with the server's own model id, declared beside `tts.model` | File ([#913](https://github.com/naveenreddyalka/daari/issues/913)) |
| 2 | **Helm has no `asr.frontierFallback`** — settings and doctor know the opt-in; the chart cannot set `DAARI_ASR__FRONTIER_FALLBACK` | 3 | 1 | LiteLLM fallback chains | Default stays off so audio never leaves the cluster; the opt-in is a values toggle like local-pool failover | File ([#914](https://github.com/naveenreddyalka/daari/issues/914)) |
| 3 | **Cancel-phase docs omit `mcp`** — `daari_cancelled_requests_total{phase="mcp"}` is recorded; metrics-prometheus lists every other phase | 2 | 1 | LiteLLM log callbacks | Agent disconnects on the local MCP path show up on the same scrape operators already chart | File ([#915](https://github.com/naveenreddyalka/daari/issues/915)) |
| 4 | **ASR guide omits Helm `asr.baseUrl`** — capacity-helm and the TTS guide name chart knobs; `backends/asr.md` does not | 2 | 1 | Cloud speech vendor docs | The local whisper page should name the same chart key the values file uses | File ([#916](https://github.com/naveenreddyalka/daari/issues/916)) |
| 5 | **Doctor `asr` row has no contract test** — the table names `frontier_fallback`, but nothing locks the wording | 1 | 1 | n/a (docs lock) | Operators rely on that row to see that audio upload is opt-in | File ([#917](https://github.com/naveenreddyalka/daari/issues/917)) |
| 6 | **Idempotency-Key, admission QoS, L1 embedder namespace, model warm, WIF / A2A / SOC 2 / admin UI** | 2–4 | 2–5 | LiteLLM / cloud | First four are already queued or in progress; compliance stays deferred | Watch |

Pruned this run: TTS route, local-pool frontier failover, OTLP logs, and the
doctor probes that shipped on 2026-09-21.

---

## Path to enterprise-grade — next 5 milestones

1. **Speech chart parity** — `asr.model` and `asr.frontierFallback` beside the TTS knobs already in the chart.
2. **Queued cache and QoS** — L1 embedding-model namespace, virtual-key admission priority, `daari models warm` (open PRs).
3. **Observability wording** — cancel-phase docs include MCP so agent disconnects match the scrape.
4. **Idempotency-Key** — still in progress on chat and Responses; do not refile.
5. **ASR operator docs** — guide and doctor table name the same Helm and frontier flags the code uses.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred.

---

## Changelog

- **2026-09-21 (speech chart parity)** — Eligible `auto-dev` backlog was empty
  (every labeled issue had an open PR). Outward: GitHub latest stable tags
  LiteLLM v1.101.0, Ollama v0.34.2, vLLM v0.29.0; no newer bar. Inward: Helm
  pins TTS model/voice but not `asr.model` or `asr.frontierFallback`;
  metrics-prometheus omits cancel phase `mcp`; ASR guide omits Helm
  `asr.baseUrl`; doctor `asr` row has no contract test. Pruned shipped TTS,
  local-pool failover, OTLP logs, and the new doctor probes. Filing five.

- **2026-09-20 (resilience + modality delta)** — Delta run 12 min after the
  17:14 sibling merged its refresh. Outward re-verified flat: LiteLLM newest
  tag v1.103.0-rc.1 (fixes/UI only, bar unchanged), Portkey v2.23.0, Kong
  2.0.3, Ollama 0.34.3 still rc, OpenRouter last moved 08-19. Inward
  (code-verified): L1 cache unversioned by embedding model, all-local-down
  hard 503 with no frontier failover, no `/v1/audio/speech`, FIFO-only
  admission gate, no OTLP logs. Verified fine: local pool LB/health/breakers,
  upgrade docs + additive migrations, L1 trim/TTL. Filing five.

- **2026-09-20 (governance secondary ingress)** — Prior cache/deadline/cancel/
  retention set confirmed shipped. Outward: LiteLLM v1.102.0 on PyPI (OCR +
  auto-router); v1.103.0-rc.1 config ownership / Fuse watch; Kong 2.0.3 and
  Ollama 0.34.2 stable (0.34.3-rc1 already mirrored). Inward: MCP route bare
  meta, batch limiter bypass + incomplete item meta, embed L0 global-only,
  Helm auth/rate/frontier gap, no proactive model warm. Filing five.

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
