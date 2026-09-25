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

## Where daari stands (verified in-tree, 2026-09-25 evening)

**Outward movers today.** **Portkey v2.25.0**: `/v1/decisions` typed-judgment
endpoint (TypeSafe Jev), `startHooks` pre-auth guardrail stage (header
allow/block + transform before authentication), gateway-local JWT request-time
workspace selection **with per-request membership enforcement**, conditional
routing on multipart form fields, bundled air-gapped pricing. **Ollama
v0.40.0-rc0**: MLX becomes the default runtime on Apple Silicon (runtime-only,
no API change — watch until stable; daari's local pool already speaks MLX).
**LiteLLM**: same-day backport wave (v1.100.3 / v1.99.4 / v1.98.1 — gpt-6
name-family fix, end-user budget-reset fixes, dep bumps); stable bar stays
**v1.102.1**, tip v1.104.0-dev.2 is fixes/price syncs. Kong 2.1.0, vLLM
0.30.0, OpenRouter (08-19) unchanged.

**Inward theme: identity edges, shutdown lifecycle, and token observability
depth** (code audit with file:line evidence). The headline defect: verified
SSO bearers early-return through `require_api_key` before the budget
pre-check and claims binding, reaching **inference** routes with no budgets,
allowlists, `no_frontier` fences, or ledger attribution (see #1103). Also
verified: no app-level drain (ready flip/admission stop on SIGTERM — Helm
`preStop` is the only story, see #1104); the usage ledger **drops**
`cached_tokens` at the SQL upsert and Prometheus/OTel have no cache-read/
cache-write token series (see #1105); Prometheus has no token counter at all
and images/moderations/rerank never call `metrics.record` (see #1106); team
binding is mint-time-only with no membership concept (see #1107).

Verified shipped today — pruned: governed `/v1/images/edits` L6 passthrough,
images cost-header pins in the shared suite, doctor images probe, morning PRD
refresh. Open backlog carries images variations, endpoint-scoped RPM/TPM
families, Anthropic-native moderations ingress, and images-edits integration
pins from the morning run.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **SSO bearers ungoverned on inference routes** — early return skips budgets/allowlists/attribution (`server/app.py` ~L259) | 5 | 2 | (nobody — daari defect) | Governance-by-default is the core claim; a verified-but-unfenced identity class breaks it | Filed — see #1103 |
| 2 | **No app-level graceful shutdown** — `/ready` never flips, admission has no drain mode, no `timeout_graceful_shutdown` | 4 | 2 | Kong / LiteLLM | Zero-dropped-request rollouts as a binary property, not a Helm-only trick | Filed — see #1104 |
| 3 | **Cached-token observability missing** — usage ledger drops `cached_tokens`; no cache_read/creation in Prom/OTel; Anthropic cache usage fields never ingested | 4 | 2 | Kong 2.1.0 | On-box FinOps evidence for the prompt-cache savings daari already prices | Filed — see #1105 |
| 4 | **No per-modality token metrics** — no `daari_tokens_total`; images/moderations/rerank invisible in `/metrics`; OTel op name hardcoded "chat" | 4 | 2 | Kong 2.1.0 | Local Grafana chargeback across chat/embed/audio/images without SaaS telemetry | Filed — see #1106 |
| 5 | **Team fixed at key-mint; no membership enforcement** — no request-time team selection, no identity↔team check (Portkey v2.25 does both) | 4 | 3 | Portkey v2.25 | Multi-team users get correct chargeback + fences on-box, no key sprawl | Filed — see #1107 |
| 6 | **Endpoint-scoped RPM/TPM families** (morning filing, open) | 4 | 3 | Portkey | Per-route quotas without a second gateway | Open — see #1099 |
| 7 | **Images variations + edits pins; Anthropic moderations ingress** (morning filings, open) | 3 | 2 | LiteLLM / cloud | Complete the creative + moderation families on one local root | Open — see #1098 / #1100 / #1101 |
| 8 | **`/v1/decisions` typed-judgment surface** — now in TWO competitors (Portkey v2.25 GA, LiteLLM Jev passthrough); daari could serve judgments from local guard/judge models | 3 | 3 | Portkey v2.25 | Typed judgments (boolean/choice/score + confidence) are a natural local-model workload | Watch (file on client demand) |
| 9 | **Pre-auth `startHooks` header policy** — allow/block + header transforms before auth (Portkey v2.25) | 3 | 2 | Portkey v2.25 | Screen traffic before spending auth/store work | Watch (file on operator ask) |
| 10 | Watch queue: MCP live-session visibility (LiteLLM tip), WIF upstream creds, A2A, SOC 2, admin UI, OpenAI Realtime/WebSocket, Ollama 0.40 MLX-default (rc) | 2–4 | 2–5 | LiteLLM / Portkey / cloud | Demand-triggered | Watch |

Pruned this run: images edits (shipped), images cost-header pins (shipped),
doctor images probe (shipped). Do not re-file closed work.

---

## Path to enterprise-grade — next 5 milestones

1. **Close the SSO governance hole** — every authenticated identity class is
   budget-fenced and attributed, or rejected on the data plane.
2. **App-level drain** — ready flip + admission stop + stream-sized grace on
   SIGTERM, on every deployment flavor.
3. **Token observability depth** — cached-token dims and per-modality token/
   spend series in Prometheus and OTel; make the new creative surface visible.
4. **Request-time team resolution** — membership-enforced team selection so
   multi-team users stop minting key sprawl.
5. **Per-route quota families + finish creative/moderation parity** — drain
   the morning backlog (endpoint RPM/TPM, variations, Anthropic moderations).

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

- **2026-09-25 evening (identity edges + shutdown + token observability)** —
  Second scan of the day (morning sibling merged the images-L6 refresh; edits
  route + cost-header pins shipped by 14:53). Outward: Portkey v2.25.0
  (decisions API, startHooks, JWT workspace membership), Ollama v0.40.0-rc0
  (MLX default on Apple Silicon, rc watch), LiteLLM stable-branch backport
  wave (bar stays v1.102.1). Inward audit filed five: SSO bearers ungoverned
  on inference (P1), app-level graceful shutdown, cached-token observability
  (usage ledger drops cached_tokens), per-modality token metrics, request-time
  team membership. New watch rows: decisions API, startHooks. Pruned three
  shipped images rows.

- **2026-09-25 morning (images L6 surface closed → next layer)** — Overnight
  drain closed the 09-24 evening modality/client-contract set plus images
  follow-ons and doctor images probe. Filed images edits/variations, creative
  metering test bar, endpoint-scoped RPM, Anthropic moderations ingress; MCP
  sessions remain watch. Edits + cost-header pins shipped same day.

- **2026-09-24 (two runs: non-chat endpoint parity; modality surface +
  client-contract honesty)** — Non-chat governance/metering/guardrails/ASR
  fence/cost headers; then images/generations, modality Idempotency-Key,
  facade 0.34 honesty, week/rpw aliases. All drained by 09-25.

- **2026-09-23 (two runs: client parameter fidelity; facade + Responses
  shapes)** — Silent drops across ingresses, then facade/Responses/MCP probe/
  stream failover. Filed ten; drained by 09-24.

- **2026-09-22 (two runs)** — Data-plane efficiency + stream truncation
  fidelity, then correlation + modality resilience. Portkey v2.24.0, Kong
  2.1.0, vLLM 0.30.0.

- **2026-09-21 (two runs)** — Data-plane hardening + lossless escalation, then
  browser/ops + agent SDK knobs.

- **2026-09-15 → 09-20 and earlier** — Condensed: governance secondary
  ingress + resilience/modality delta; embed/ASR measurement + cache tenancy
  + request lifecycle; soft-budget drain + governance/chargeback theme; loop
  restructure (never-empty refill + scheduled Actions prd run); fleet-auth,
  fleet story, resilience + metering, stored-artifact tenancy, Batch/Files
  API, pricing refresh, session affinity, stall escalation, MCP pagination,
  Apache 2.0 relicense, this PRD's creation (2026-08-28).
