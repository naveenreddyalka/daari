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

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **MCP `route` skips virtual-key governance** — `_run_tool` builds bare `RequestMeta(deadline_ms=…)`; no `apply_auth_claims_to_meta`, model allowlist, spend attribution, or tenant cache | 5 | 3 | LiteLLM MCP gateway (team toolsets); Kong agentic policies | Shared on-prem MCP front door needs the same key/team fences as chat before agents hit local GPUs | File |
| 2 | **Batch drain bypasses RPM/TPM/RPD + incomplete meta** — worker calls `router.route` without the limiter; item meta omits `key_id`/`team_id`/`cache_scope` even though `BatchGovernance` stores `key_id` | 5 | 3 | LiteLLM batch + budgets; OpenAI Batch quotas | Overnight local eval must not be a quota-evasion lane vs interactive chat | File |
| 3 | **Embed L0 is tenant-blind** — `embedding_cache_request()` never sets `RequestMeta`; scoped keys still share vectors across teams | 4 | 2 | Portkey workspace cache; LiteLLM cache metadata | Embeddings feed L1 and tool-search; cross-tenant hits leak without frontier egress | File |
| 4 | **Helm missing auth / rate-limit / frontier knobs** — chart has redis, postgres, deadline, ASR; no `apiKeySecret`, `rateLimit.*`, or `frontier.enabled` + secret | 4 | 2 | Kong Konnect / LiteLLM Helm | K8s operators should wire fleet auth and caps without hand-patched Deployments | File |
| 5 | **No proactive model warm** — warm preference is reactive via `/api/ps`; cold Ollama TTFT stays the worst first-request UX | 3 | 2 | Ollama `keep_alive` / vLLM preload | Local-first product owns cold start; one CLI/onboard step beats a cloud warm pool | File |
| 6 | **Doctor silent on new ops knobs / OCR / Fuse routing / WIF / A2A / SOC 2 / admin UI** | 2–4 | 2–5 | LiteLLM / cloud | Doctor warn is next-tranche; OCR+Fuse stay watch; compliance deferred | Watch |

Pruned this run: tenant cache, selective invalidate, request deadline,
disconnect cancel (non-facade), request-log retention, thinking `/api/show`
(shipped). Facade disconnect and Idempotency-Key stay open elsewhere.

---

## Path to enterprise-grade — next 5 milestones

1. **MCP governance parity** — virtual-key claims, allowlists, spend, and `cache_scope` on MCP `tools/call` / `route`.
2. **Batch quota + meta replay** — drain path charges RPM/TPM/RPD and copies tenant fields onto every item.
3. **Scoped embed cache** — L0 embed keys honor `cache_scope` like chat.
4. **Helm fleet auth surface** — Secret-backed master key, rate-limit Redis, frontier enable/key.
5. **`daari models warm`** — preload configured L3–L5 (+ embed) before serve/onboard.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

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
