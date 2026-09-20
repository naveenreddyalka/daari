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

## Where daari stands (verified in-tree, 2026-09-20)

Cache tenancy (`cache_scope`), selective invalidate, request deadline (chat /
audio / embed / MCP / facade), disconnect cancel (OpenAI chat, MCP, embed/ASR),
request-log retention, Redis L0 age prune, thinking controls on `/api/show`,
spend `--tier`, and ASR frontier validate are shipped. Still open and not
restated below: Idempotency-Key, facade non-stream disconnect, and a thin
P3 docs/test tail.

**Outward (this run):** LiteLLM **v1.102.0** is on PyPI (auto-router controls,
native OCR, gateway reliability); GitHub's latest non-prerelease tag still
reads v1.101.0 — treat docs/PyPI as the bar. **v1.103.0-rc.1** adds config-file
ownership and Fuse/capability routing (watch). Kong **2.0.3** and Portkey
enterprise unchanged. Ollama stable **v0.34.2**; **v0.34.3-rc1** thinking
controls already mirrored in-tree. vLLM **0.29.0** flat. OpenRouter US/EU
in-region routing is cloud-only; daari already has `region_pin`.

**Inward theme: governance holes on secondary ingress.** Chat/Responses/
Anthropic got virtual-key meta, allowlists, and tenant cache; MCP `route` and
batch item drain did not. Embed L0 is still global-scoped. Helm wires redis /
postgres / deadline / ASR but not master API key, rate-limit Redis, or
frontier. Doctor never warns when deadline is unset or scoped cache meets
disk+multi-replica. Cold TTFT still has no proactive `models warm`.

**Delta run (17:26), theme: resilience and modality seams.** The L1 semantic
cache never records its embedding model — `semantic_context_key` omits
`cache.l1.embedding_model`, so swapping the embedder leaves stale vectors
matching garbage (upgrade.md documents the hazard instead of fixing it).
All-local-hosts-down is a hard 503 `backend_unavailable` with no opt-in
frontier failover (ASR already has `asr.frontier_fallback`; chat does not).
No `/v1/audio/speech` despite shipped ASR. The global in-flight gate is
FIFO-only (no per-key priority; batch drain bypasses it, only idle-yields).
OTel exports traces + metrics but not logs — gateway events reach
Datadog/Splunk only via file tail or stdout sidecar. Verified fine, not
filed: local pool multi-host LB/health/breakers shipped; upgrade docs +
additive `_migrate()` solid (no `daari migrate` demand yet); L1 has
`max_entries` FIFO trim + TTL prune.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **L1 semantic cache unversioned by embedder** — `semantic_context_key` and stored entries omit `cache.l1.embedding_model`; swapping the embed model keeps stale vectors live (wrong hits / dimension mismatch) | 4 | 2 | GPTCache (index per embedder); hosted semantic caches | Local embed models get swapped often; correctness across swaps keeps the shared org cache trustworthy | File ([#845](https://github.com/naveenreddyalka/daari/issues/845)) |
| 2 | **All local hosts down = hard 503** — pool exhaustion raises `BackendUnavailable`; no opt-in frontier failover for chat (ASR already has `asr.frontier_fallback`) | 4 | 2 | LiteLLM fallback chains; Kong upstream failover | HA without a second GPU box: outage degrades to governed frontier (scrub/budgets/allowlists intact) | File ([#846](https://github.com/naveenreddyalka/daari/issues/846)) |
| 3 | **No `/v1/audio/speech`** — ASR shipped both directions, TTS absent; openedai-speech/Kokoro serve the exact OpenAI shape locally | 4 | 3 | Portkey (ElevenLabs native); OpenRouter `/audio/speech` | Voice loop (STT→chat→TTS) through one governed box; $0/char, same keys and chargeback | File ([#847](https://github.com/naveenreddyalka/daari/issues/847)) |
| 4 | **Admission gate is FIFO-only** — single `asyncio.Condition`, no per-key/team priority; batch drain bypasses the in-flight cap (idle-yield only) | 4 | 3 | vLLM priority scheduling; Kong route priority | One GPU serves IDE + overnight eval; interactive turns must preempt at the gate | File ([#848](https://github.com/naveenreddyalka/daari/issues/848)) |
| 5 | **No OTLP logs signal** — request events are file JSONL + optional stdout; OTel exports traces/metrics only | 3 | 2 | LiteLLM log callbacks; cloud gateways | Same collector already deployed for daari traces — third signal completes the story, no sidecars | File ([#849](https://github.com/naveenreddyalka/daari/issues/849)) |
| 6 | **Doctor ops warns / moderations + rerank endpoints / `daari migrate` + skew guard / ASR pool HA / OCR / Fuse routing / WIF / A2A / SOC 2 / admin UI** | 2–4 | 2–5 | LiteLLM / Cohere / cloud | Moderations-vs-guardrails and migrate tooling wait for buyer demand; rest deferred | Watch |

Pruned this run: the governance secondary-ingress rows (MCP route, batch
quota+meta, embed L0 scope, Helm knobs, model warm) — all five filed as
issues by the 17:14 sibling run and now queued.

---

## Path to enterprise-grade — next 5 milestones

1. **Governance secondary-ingress set** (queued) — MCP route claims, batch quota+meta, scoped embed L0, Helm auth knobs, model warm.
2. **Cache correctness across embedder swaps** — L1 entries namespaced by embedding model.
3. **Local-outage failover** — opt-in frontier escalation when every local host is down, fences intact.
4. **QoS at the gate** — per-key priority classes on the in-flight cap; batch charged at low priority.
5. **Voice + logs completeness** — `/v1/audio/speech` local TTS and OTLP logs alongside traces/metrics.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

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
