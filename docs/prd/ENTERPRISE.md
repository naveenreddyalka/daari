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

## Where daari stands (verified in-tree, 2026-10-08)

**Loop velocity.** Decisions governance landed the same day it was filed:
guardrails + OTel + local retry + `user` spend on `/v1/decisions`, plus
`gpt-6-luna-decisions` alias normalization. Rows 44–48 (surface launch) and
row 49 (governance) are Shipped. Still open from the morning drain: fleet MCP
OAuth denylist, admin keys/teams pagination+audit, multi_agent L6 metering,
Decisions doctor/Helm/auth docs. Hot-reload `config.yaml` stays in flight;
Messages `mcp_servers` tool allowlist stays parked.

**Outward.** Anthropic **Haiku 5.5** (7 Oct) is live at $0.10/$0.50 (≤100K) with
a 100K prompt threshold, effort levels, and halved Sonnet/Opus 5.5 cache reads
($0.10 / $0.20) — daari's catalog still bills those cache reads at the old
0.1× rates and has **no** `claude-haiku-5-5` row. Anthropic Models API + SDK
1.12.0 added `capabilities.server_tools` and lifecycle stage fields/filters.
OpenAI refreshed `chat-latest` (7 Oct) and documents Luna chat cache reads at
$0.01/MTok — daari's chat row omits `cached_input_per_1m` (bills at input).
LiteLLM stable remains **v1.104.2** (decisions/systemone backport); 1.105 is
still RC (rc.3). Portkey v2.28.0 / Ollama 0.40.1 / Kong 2.2.0 / OpenRouter
audio (ElevenLabs 7 Oct) — no new gateway-control-plane delta that beats
on-box catalog truth this run.

**Inward theme: catalog truth + Decisions cost depth.** Code audit confirms
sonnet/opus-5-5 `cached_input_per_1m` at 0.20/0.40; luna chat has no cached
rate; Anthropic-native cards emit only `thinking.types.disabled`; `/v1/decisions`
has no L0 exact cache despite being the ideal typed-repeat workload.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 54 | claude-haiku-5-5 catalog (100K-threshold rates, caps, param compat) + reprice sonnet/opus-5-5 cache reads | 5 | 1 | Anthropic pricing (7 Oct); LiteLLM day-one catalogs | Cost-true routing on the new cheap tier | Filed [#1505](https://github.com/naveenreddyalka/daari/issues/1505) |
| 55 | gpt-6-luna chat/responses `cached_input_per_1m` = $0.01 (keep Decisions input-only overlay) | 4 | 1 | OpenAI list pricing | Ledger matches provider invoices on cache hits | Filed [#1506](https://github.com/naveenreddyalka/daari/issues/1506) |
| 56 | Anthropic `/v1/models`: `server_tools` + lifecycle fields/filter | 4 | 2 | Anthropic Models API / SDK 1.12.0 | Local catalog honesty for Claude Code | Filed [#1507](https://github.com/naveenreddyalka/daari/issues/1507) |
| 57 | Decisions L0 exact cache for identical typed requests | 4 | 2 | — (cloud gateways proxy, don't short-circuit) | Zero-token repeats for classifier harnesses | Filed [#1508](https://github.com/naveenreddyalka/daari/issues/1508) |
| 58 | Map OpenAI `chat-latest` rolling alias in catalog/pricing | 3 | 1 | OpenAI changelog (7 Oct) | BYOK IDEs send the alias as-is | Filed [#1509](https://github.com/naveenreddyalka/daari/issues/1509) |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist (Redis/Postgres) | 5 | 3 | Kong Token Vault; LiteLLM shared revoke stores | Revoke must stick across Helm replicas | Filed [#1498](https://github.com/naveenreddyalka/daari/issues/1498) |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM proxy admin UI audit trail | Control-plane honesty at key-store scale | Filed [#1499](https://github.com/naveenreddyalka/daari/issues/1499) |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage; LiteLLM agent cost split | FinOps chargeback for delegated agents | Filed [#1500](https://github.com/naveenreddyalka/daari/issues/1500) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface before rate-family miss | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
| 49 | Guardrails + OTel (+ local retry) + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong policy on decisions `state` | Same on-box policy engine as systemone/OCR | Shipped |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta; LiteLLM v1.104.2 | Typed judgments on-box | Shipped |
| 45 | MCP OAuth scope + RFC 7009 revocation | 4 | 2 | LiteLLM / Kong | On-box revoke/scope | Shipped |
| 46 | OTel + guardrails + retry on `/mcp/proxy` + `/v1/systemone` | 4 | 2 | Kong / Portkey | Local policy latency | Shipped |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM admin UI | Same-box console | Shipped |
| 48 | Responses multi-agent forward or honest 400 | 3 | 2 | OpenAI multi-agent beta | Transparent L6 delegation | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): `/v1/decisions` + luna pricing (incl.
input-only decisions billing + alias normalize); decisions guardrails/OTel/
retry/`user`; MCP OAuth scope/revoke endpoint; systemone/mcp_proxy/OCR
hardening; admin read plane existence; multi-agent forward; Anthropic
`thinking.types.disabled`; age-encrypt backup test; web-ui CSP/sessionStorage;
classifier Prom series; grok-4.7 / claude-opus-5-5 / claude-sonnet-5-5 catalog
entries (rates need the 7-Oct cache reprice — row 54).

Watch rows (do not file yet): Decisions stream/batch/Ollama/Anthropic facades;
gpt-6-luna Decisions schema drift while the beta hardens; Anthropic SDK
browser/computer-use toolsets (client-side loop — passthrough unaffected);
LiteLLM 1.105 stable + M365 MCP catalog (file at GA); Portkey JWT just-in-time
access + `/v1/health` `last_synced_at` (file on operator ask); OpenRouter
ElevenLabs audio passthrough (only if BYOK clients demand it); OpenAI
in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: Prom `decisions` modality +
`rate_families` mapping; luna Decisions input-only overlay; revoke
`_prune_revoked` TTL cleanup; web-ui Bearer in memory / opt-in
`sessionStorage`; `/v1/decisions` listed in http-api.md; batches still
chat-only by design; threshold pricing path (`input_threshold_tokens`) ready
for Haiku 100K (astra pattern).

---

## Path to enterprise-grade — next 5 milestones

1. **Catalog truth after the 7-Oct reprice** — Haiku 5.5 + sonnet/opus cache
   reads (row 54) and luna chat cached input (row 55): live billing defects.
2. **Anthropic Models API depth** — `server_tools` + lifecycle filter (row 56)
   so Claude Code sees a first-party-shaped local catalog.
3. **Decisions cost depth** — L0 exact cache (row 57) once governance is
   shipped; then `chat-latest` alias honesty (row 58).
4. **MCP revoke that survives replicas** — durable jti denylist (row 50) so
   Helm `replicaCount>1` and restarts keep revocations.
5. **Admin + FinOps + ops** — pagination/audit (row 51), multi-agent metering
   (row 52), Decisions doctor/Helm (row 53), then hot-reload (row 6).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-08 (catalog truth after Haiku 5.5)** — Row 49 marked Shipped
  (decisions governance). Filed rows 54–58: Haiku 5.5 + sonnet/opus cache
  reprice, luna chat cached input, Anthropic server_tools/lifecycle,
  Decisions L0 cache, `chat-latest` alias. Outward: Anthropic Haiku 5.5 +
  Models API lifecycle/server_tools; OpenAI `chat-latest` refresh; LiteLLM
  1.105 still RC; OpenRouter ElevenLabs audio (watch).

- **2026-10-08 (depth on shipped Decisions / OAuth / admin / multi-agent)** —
  Rows 44–48 marked Shipped. Inward audit filed rows 49–53. Outward: LiteLLM
  v1.104.2 decisions/systemone backport; Haiku 5.5 queued as row 54; Portkey
  v2.28.0; Ollama 0.40.1.

- **2026-10-07 (decisions surface + lifecycle depth)** — Filed rows 44–48
  (local-first `/v1/decisions`, MCP OAuth scope/revocation, new-surface
  spans/guardrails/retry, web-ui admin read plane, Responses multi-agent).

- **2026-10-06 → 08-28** — Condensed: catalog + classifier/watchdog; admin-plane
  + OCR governance; operate-gates + FinOps; LiteLLM 1.104; OBO/classifier;
  decision models + MCP OAuth; Apache 2.0; this PRD's creation.
