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

**Loop velocity.** Rows 44–48 (filed 10-07) all landed on `main` within a day:
`/v1/decisions` + gpt-6-luna pricing (incl. the decisions input-only billing
path), MCP OAuth scope enforcement + RFC 7009 revoke, OTel/guardrails/retry on
`/mcp/proxy` + `/v1/systemone`, the web-ui keys/teams admin read plane, and
Responses multi-agent forward-or-400. Anthropic `thinking.types.disabled` on
native `/v1/models` and the age-encrypt backup round-trip test shipped too.
Hot-reload `config.yaml` stays in flight; the Messages `mcp_servers` tool
allowlist stays parked.

**Outward.** **LiteLLM backported `/v1/systemone`, OpenAI-format
`/v1/decisions`, and the OpenAI Decisions provider to stable v1.104.2 (8 Oct)**
— every major competitor now ships a decisions surface; daari reached parity
first and differentiation moves to governance depth. **Anthropic launched
Claude Haiku 5.5 (7 Oct)** — $0.10/$0.50 per MTok with a 100K-token prompt
threshold (5× above it), 1M context, 128K output, adaptive thinking — **and
halved cache-read pricing on Sonnet 5.5 ($0.10) and Opus 5.5 ($0.20)**, so
daari's shipped rates now overbill cache reads 2×. Anthropic Models API added
`capabilities.server_tools` + lifecycle-stage fields/filter; SDKs added beta
browser/computer-use toolsets (client-side loops — passthrough unaffected).
OpenAI added a `chat-latest` rolling snapshot alias (7 Oct). Portkey moved to
**v2.28.0** (AWS OAuth client-credentials, JWT just-in-time service access,
`DISABLE_TIKTOKEN` chars/4 estimator). Ollama **0.40.1 stable** (cloud
usage/balance proxying — facade unaffected). Kong 2.2.0 / OpenRouter (08-19) /
MCP blog (08-22) flat.

**Inward theme: depth on the surfaces that just shipped.** Code audit (10-08)
confirmed: `/v1/decisions` meters the Prom `decisions` modality but skips
guardrails/OTel, hardcodes spend `user_id=""`, and its local path bypasses
systemone hardening; the MCP OAuth revoked-jti denylist is a process-local
dict (`mcp_oauth.py` ~L41) — revocation does not replicate across Helm
replicas and is forgotten on restart; admin `GET /v1/daari/keys`/`teams` dumps
are unpaginated and unaudited; multi_agent L6 reads only top-level usage;
doctor/Helm/auth-and-keys docs lag the Decisions family.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 54 | claude-haiku-5-5 catalog (100K-threshold rates, caps, param compat) + reprice sonnet/opus-5-5 cache reads | 5 | 1 | Anthropic pricing page (7 Oct); LiteLLM day-one catalogs | Cost-true routing and honest cache savings on the new cheap tier | File next run (10-08 issue budget spent) |
| 49 | Guardrails + OTel (+ local retry) + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong policy on decisions `state`; OCR parity in-tree | Same on-box policy engine as systemone/OCR | Filed [#1497](https://github.com/naveenreddyalka/daari/issues/1497) |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist (Redis/Postgres) | 5 | 3 | Kong Token Vault; LiteLLM shared revoke stores | Revoke must stick across Helm replicas | Filed [#1498](https://github.com/naveenreddyalka/daari/issues/1498) |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM proxy admin UI audit trail | Control-plane honesty at key-store scale | Done [#1499](https://github.com/naveenreddyalka/daari/issues/1499) |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage; LiteLLM agent cost split | FinOps chargeback for delegated agents | Done [#1500](https://github.com/naveenreddyalka/daari/issues/1500) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface before rate-family miss | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta; LiteLLM v1.104.2 | Typed judgments on-box | Shipped |
| 45 | MCP OAuth scope + RFC 7009 revocation | 4 | 2 | LiteLLM / Kong | On-box revoke/scope | Shipped |
| 46 | OTel + guardrails + retry on `/mcp/proxy` + `/v1/systemone` | 4 | 2 | Kong / Portkey | Local policy latency | Shipped |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM admin UI | Same-box console | Shipped |
| 48 | Responses multi-agent forward or honest 400 | 3 | 2 | OpenAI multi-agent beta | Transparent L6 delegation | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | Shipped | Shipped |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | Shipped | Shipped |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | Shipped | Shipped |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | Shipped | Shipped |
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | Shipped | Shipped |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | Shipped | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): `/v1/decisions` + luna pricing (incl.
input-only decisions billing); MCP OAuth scope/revoke endpoint;
systemone/mcp_proxy/OCR hardening stacks; admin read plane existence;
multi-agent forward; Anthropic `thinking.types.disabled`; age-encrypt backup
test; web-ui CSP/sessionStorage; classifier Prom series; grok-4.7 /
claude-opus-5-5 / claude-sonnet-5-5 catalog entries (rates now need the 7-Oct
cache reprice — row 54).

Watch rows (do not file yet): Decisions L0/exact cache (strong local-first
angle once governance lands); Decisions stream/batch/Ollama/Anthropic facades;
admin dedicated rate family; gpt-6-luna Decisions schema drift while the beta
hardens; OpenAI `chat-latest` alias pricing (rolling snapshot — map when a
client sends it); Anthropic Models API `server_tools` + lifecycle-stage parity
on native `/v1/models` (fold into row-54 catalog sweep or next one); Anthropic
SDK browser/computer-use toolsets (client-side loop — passthrough unaffected);
LiteLLM 1.105/1.106 M365 MCP catalog + scoped-SQL tracing (file at GA);
Portkey v2.28.0 JWT just-in-time access + `/v1/health` `last_synced_at` (file
on operator ask); OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: Prom `decisions` modality +
`rate_families` mapping; luna in `_DEFAULT_MODEL_PRICES` with decisions
billing path; revoke `_prune_revoked` TTL cleanup; web-ui Bearer in memory /
opt-in `sessionStorage` (no localStorage); `/v1/decisions` listed in
http-api.md; batches still chat-only by design (`_execute_batch_chat_body`).

---

## Path to enterprise-grade — next 5 milestones

1. **Catalog truth after the 7-Oct reprice** — add claude-haiku-5-5 with its
   100K-threshold rates and fix sonnet/opus-5-5 cache reads (row 54): shipped
   rates currently overbill cache reads 2×, a live billing-correctness defect.
2. **Decisions governance parity** — guardrails + OTel + local retry + `user`
   spend on `/v1/decisions` (row 49), matching systemone/OCR, now that
   LiteLLM v1.104.2 ships the same surface without on-box policy.
3. **MCP revoke that survives replicas** — durable jti denylist (row 50) so
   Helm `replicaCount>1` and restarts keep revocations.
4. **Admin read plane at scale** — pagination + audit events (row 51), then
   multi-agent FinOps metering (row 52).
5. **Ops discoverability** — doctor/Helm/auth-and-keys for Decisions (row 53),
   then hot-reload (row 6) and the parked Messages tool allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-08 (depth on shipped Decisions / OAuth / admin / multi-agent)** —
  Rows 44–48 marked Shipped (drained in under a day). Inward audit filed rows
  49–53: decisions guardrails/OTel/user-spend, fleet OAuth denylist, admin
  pagination/audit, multi_agent spend metering, decisions ops docs. Outward:
  LiteLLM v1.104.2 backports decisions/systemone to stable (bar moves);
  Anthropic Haiku 5.5 + Sonnet/Opus cache-read reprice → row 54 queued for
  the next run's budget; Portkey v2.28.0; Ollama 0.40.1.

- **2026-10-07 (decisions surface + lifecycle depth)** — Filed rows 44–48
  (local-first `/v1/decisions`, MCP OAuth scope/revocation, new-surface
  spans/guardrails/retry, web-ui admin read plane, Responses multi-agent).

- **2026-10-06 → 08-28** — Condensed: catalog + classifier/watchdog; admin-plane
  + OCR governance; operate-gates + FinOps; LiteLLM 1.104; OBO/classifier;
  decision models + MCP OAuth; Apache 2.0; this PRD's creation.
