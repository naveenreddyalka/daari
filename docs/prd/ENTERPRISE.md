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

## Where daari stands (verified in-tree, 2026-10-25)

**Loop velocity.** The whole 10-24 backlog merged overnight: eMudhra egress
distrust, console enforcement inventory + cache-invalidate form, Postgres
`schema_ok` gate + `migrate --downgrade`, fleet-shared breakers via Redis,
Phonon voice catalog, per-end-user RPD, hardened completion-webhook delivery,
replay-safe org webhook ingest, and the TTS body/input bounds. Only the
strip-visibility/Decisions-cost row is still open from that wave.

**Outward.** LiteLLM **1.106.4** (2026-10-25, backports 1.103.9/1.104.7/
1.105.5): startup ImportError fix plus **image-scan hygiene — the emSign ECC
Root CA is scrubbed from their images** (brotli 1.2.0, lockfile cleanup);
1.107.0 stays do-not-install. Ollama **0.40.11 GA** (10-24): speech +
**d3 decision models GA** (2B/4B/9B/27B) — daari already ships both. OpenAI
10-24: **Enterprise Key Management** (external KMS over stored content) and
**UK data residency** (`gb.api.openai.com`, 10 regions, 10% uplift — daari's
free-form residency labels + 1.10× uplift already handle it); 10-23 spec adds
`/agents/automations` (cron automations). Prisma AIRS (October): Istio mesh,
**Agent Identity Security** (per-agent OAuth 2.1 identity, per user-agent-pair
MCP tool policy, dual-attribution audit), streamed chunk-level response
inspection — daari's incremental guardrail `stream_mode` already relays safe
chunks. Kong 2.2 passthrough mode + Token Vault (daari: `l6_passthrough` +
`secret://` cover the shape). Anthropic flat since 10-22; SDK 2.2.0's
dimension-grouped usage/cost reports deprecate the legacy flat reports.

**Inward theme: prove the wave, then report on it.** Ten features merged with
zero gateway-flow integration coverage (92 cases, none touch TTS/webhooks/
decisions-GA/user_rpd/breakers/schema_ok; the streamed-TTS spend row is never
asserted anywhere). The fleet breakers beyond systemone are invisible —
no state gauge, panel, alert, doctor check, or reset. FinOps is row-level
only: no `--group-by`, no time buckets, and `service_tier` is priced but
never persisted. The per-user fences read only OpenAI's top-level `user` —
Anthropic `metadata.user_id` traffic gets no user RPD/cap at all. And the
image we ship still carries the emSign roots daari distrusts at runtime.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 212 | Doctor: `responses_completion_webhook_url` without signing secret | 3 | 1 | LiteLLM / Svix webhook hygiene | Same doctor pass as budget/key-expiry | Filed [#1934](https://github.com/naveenreddyalka/daari/issues/1934) (pm run) |
| 213 | Grafana + PrometheusRule for completion / org webhook counters | 3 | 1 | Kong / cloud webhook dashboards | Counters already exported; packaging | Filed [#1935](https://github.com/naveenreddyalka/daari/issues/1935) (pm run) |
| 214 | Phonon multilingual tags + doctor CC BY-NC tip for 40m | 3 | 2 | OpenAI TTS / Ollama 0.40.11 | Local voice behind daari auth/budgets | Filed [#1936](https://github.com/naveenreddyalka/daari/issues/1936) (pm run) |
| 215 | AAIF Agent Skills packages (`SKILL.md` in subdirs) | 3 | 2 | Claude / AAIF skill loaders | One on-disk tree for IDE + daemon | Filed [#1937](https://github.com/naveenreddyalka/daari/issues/1937) (pm run) |
| 216 | Hermetic TTS speech micro-benchmark (stream finalize + voices) | 2 | 1 | — (testability) | Opt-in benchmark suite already hermetic | Filed [#1938](https://github.com/naveenreddyalka/daari/issues/1938) (pm run) |
| 207 | Strip eMudhra/emSign from image trust stores (certifi + Debian) + compare floor 1.106.4 | 4 | 1 | LiteLLM 1.106.4 images | Build-time scrub reuses the in-tree runtime filter; no base-image wait | Filed [#1929](https://github.com/naveenreddyalka/daari/issues/1929) |
| 208 | Gateway-flow integration coverage for the merged wave (TTS spend, webhooks, ingest, decisions GA, stream cache-write, user_rpd, fleet breakers, schema_ok) | 4 | 2 | — (regression fence) | All mockable in-process; the fence that lets the loop merge daily | Filed [#1930](https://github.com/naveenreddyalka/daari/issues/1930) |
| 209 | Dimension-grouped spend reports + time buckets; persist `service_tier` in the ledger | 4 | 2 | Anthropic Admin API / LiteLLM daily usage | GROUP BY over the on-box ledger; no raw-row export to a SaaS | Filed [#1931](https://github.com/naveenreddyalka/daari/issues/1931) |
| 210 | Per-family breaker state gauge, panel, alert, doctor, inventory + reset (frontier/local/MCP) | 4 | 2 | Kong upstream health | Breakers already share the cache Redis; read state we already keep | Filed [#1932](https://github.com/naveenreddyalka/daari/issues/1932) |
| 211 | Anthropic `metadata.user_id` → per-user fences; `user_rpd` in keys list + web-ui | 3 | 2 | OpenRouter / LiteLLM | One user bucket across both SDK doors, no client changes | Filed [#1933](https://github.com/naveenreddyalka/daari/issues/1933) |
| 206 | Client-visible content-strip warnings + Decisions reported-cost billing + live model-list 400 | 3 | 2 | OpenRouter transform warnings / OpenAI usage-true billing | `daari_meta.warning` + labeled counters exist; honesty end to end | Open (filed 10-24) |
| 198–205 | eMudhra egress distrust; fleet breakers; Phonon voices; compare 1.106.3; user RPD; webhook delivery + ingest hardening; TTS bounds | 3–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, HA share, local voice, push channels | Shipped |
| — | Web-ui enforcement inventory + cache-invalidate form; Postgres `schema_ok` + `migrate --downgrade` | 3 | 2 | LiteLLM admin UI / migrate story | Same-box console; ready truth for PG fleets | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): **Responses background-job lease/orphan
reclaim** — jobs persist "queued" then terminal only; no in_progress
transition, no heartbeat, a dead owning pod leaves the job queued fleet-wide
(`responses.py` ~L1176/1390; file on fleet-ops ask); **at-rest encryption of
daari stores** (OpenAI EKM analog — cache/ledger/request-log/response store
encrypt-at-rest with customer KMS; regulated-buyer ask); OpenAI
`/agents/automations` passthrough (spec 10-23; demand-triggered); Prisma AIRS
**Agent Identity Security** (per-agent OAuth 2.1 identity + dual-attribution
audit; adjacent to the parked per-key tool allowlist row); web-ui voices list
(`/v1/audio/voices` exists, console never fetches it — minor); `daari_schema_ok`
gauge HELP text still says "SQLite" though it covers PG skew; UK residency
doc note (`gb` works via free-form labels); Anthropic threads are **Managed
Agents session threads + SSE**, not Messages API threads (pm-run correction);
**Claude Models on Google Cloud** as a frontier flavor (IAM-auth egress —
buyer ask); Open Responses WebSocket; Anthropic OTel export beta parity; Prometheus
exemplars + `gen_ai.agent.*`; LiteLLM 1.107-rebuild watchables (ID-JAG /
OAuth-delegate / `agent_access_default_deny`); Portkey WIF upstream creds;
SCIM + multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter
Private Endpoints as an L6 slot recipe; certifi upstream drop of emSign
roots (image scrub filed as row 207 regardless).

Verified fine this run — don't re-audit: OpenAI 12-hour prompt caching
already billed (`cache_write_12h_per_1m` 2.5×, `prompt_cache_retention`
forwarded, #1843); incremental streaming guardrails exist (`stream_mode:
"incremental"` holdback window — Prisma AIRS streamed-inspection parity);
residency free-form labels + 1.10× regional uplift cover the new `gb`
endpoint; d3 GA sizes (2b/4b/9b/27b) all in `BUILTIN_LOCAL_MODELS` +
pricing; `schema_ok` observability complete (Prom gauge, Grafana panel,
PrometheusRule, web-ui banner, `/ready`, doctor — incl. PG skew); Responses
background jobs poll cross-pod via the persisted response store (queued +
terminal states; gap is lease/reclaim only); `/v1/audio/voices` with live
Phonon discovery + unknown-voice 400 + doctor tip; per-user request counts in
`report.users` + `spend report --by-user`; `keys create/update --user-rpd`.

---

## Path to enterprise-grade — next 5 milestones

1. **Scanner-clean supply chain** — strip the distrusted roots from the
   shipped image and bump the compare floor to 1.106.4 (row 207).
2. **Prove the wave, package its day-2** — gateway-flow integration coverage
   for all ten just-merged features, incl. the never-asserted streamed-TTS
   spend row (row 208); webhook doctor parity + panels (rows 212–213).
3. **Report like an Admin API** — dimension-grouped, time-bucketed spend
   reports over the on-box ledger with `service_tier` persisted (row 209).
4. **Operate the breakers** — state, alerts, doctor, inventory and reset
   for every breaker family, not just systemone (row 210).
5. **One user fence on both doors** — Anthropic `metadata.user_id`
   attribution + admin visibility (row 211), then strip/billing honesty
   (row 206) and the 10-10 tenancy set (62–67).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, full AAIF Skills/Open Responses WS) stay deferred
until buyer demand.

---

## Changelog

- **2026-10-25 (prove the wave, report on it, ship a clean image)** — Marked
  rows 198–205 and the console/PG pair Shipped (whole 10-24 backlog merged
  overnight). Outward: LiteLLM 1.106.4 image-scan hygiene (emSign scrubbed
  from their images); Ollama 0.40.11 GA (daari already at parity on speech +
  d3); OpenAI EKM + UK residency + `/agents/automations`; Prisma AIRS Agent
  Identity Security + streamed inspection (daari incremental guardrails
  already relay). Filed rows 207–211: image trust-store scrub, wave
  integration coverage, grouped spend reports, breaker observability,
  Anthropic per-user attribution. New watch rows: background-job lease
  reclaim, EKM-analog at-rest encryption, agents/automations passthrough.
  A same-day pm sibling filed rows 212–216 (webhook doctor secret parity,
  webhook Grafana/alerts, Phonon multilingual + CC BY-NC tip, AAIF Agent
  Skills packages, hermetic TTS benchmark) — adopted here because the pm
  PRD branch pruned the pinned compact/MCP rows and fails the pin test.

- **2026-10-24 + pm (trust floors, HA share, local voice; push channels)** —
  Marked rows 191–197 Shipped. Outward: LiteLLM 1.106.3 GA floor (cosign
  `e82a3c6`, eMudhra CA removed); Ollama 0.40.10/0.40.11-rc0; AAIF Skills +
  Open Responses WS; Anthropic SDK 2.2.0/2.3.0 (message threads, grouped
  usage/cost reports, Claude Tags), Claude on Google Cloud, Bearer-auth SDK
  switch verified handled. Filed rows 198–206 across both runs; the pm
  breaker filing was a duplicate of row 199 and needs a human close.

- **2026-10-23 (bill what was served, speak what went GA)** — Marked rows
  183–190 Shipped. Outward: Ollama 0.40.9; OpenAI Decisions GA; semantic-
  router 1.0/1.1. Filed rows 193–197.

- **2026-10-22 → 08-28** — Condensed: finish-the-truths, console and day-2
  packaging; breaker truth, invoice-true cache billing, user profiles;
  LiteLLM compromise + Anthropic API-version footgun; finish-the-knobs;
  decisions depth; `resultType`/egress waves; Apache 2.0; this PRD's
  creation.
