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

## Where daari stands (verified in-tree, 2026-10-23)

**Loop velocity.** Both 10-22 waves are merged: the morning set (streamed
cache-write TTL billing, enforcement sync, service-tier degrade, Redis
breaker, sampling-strip telemetry) and the pm console/packaging set (web-ui
spend `team`/`until` + breaker reset, Grafana gzip + TTL panels, vLLM
security floor doc) all closed within a day. Open backlog: #1874/#1875
(fleet Responses cancel, enforcement webhook ingest) plus the 10-10
tenancy/console set, all `agent:working`.

**Outward.** Ollama 0.40.9 went stable: local speech via Phonon on a
streaming OpenAI-compatible `/v1/audio/speech`, the **d3 decision-model
family** (vLLM Semantic Router lineage, 2B–27B), Flint on Linux/Windows,
and streamed-failure reporting on its Responses/Anthropic facades. OpenAI's
**Decisions API went GA 10-22** (`input_json`, images in per-question
instructions, 400-question ceiling, shared-input cache discounts). The
eMudhra (emSign) CA distrust (10-20) pushed Portkey v2.29.1 and Kong
trust-store updates — certifi 2026.10.23 still ships the roots, so daari
watches. semantic-router hit 1.0/1.1 (composable scored routers, Mongo
index). LiteLLM still has no clean post-compromise 1.107 (floor 1.106.2);
vLLM 0.32.0, Kong 3.16.0.1, OpenRouter, Anthropic, MCP flat.

**Inward theme: bill what was served, speak what went GA.** After a
`service_tier` degrade the spend ledger still bills the *requested* tier and
stream cost headers omit tier entirely — the one place #1879's truth didn't
reach. Decisions requests in the GA shape silently drop `input_json`
(`extra="ignore"`) and reject per-question images. The TTS relay buffers
full audio against a now-streaming local backend. New soft_warning kinds and
the enforced-profiles gauge have no panels or alert rules.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 193 | Bill served `service_tier` on spend ledger + stream cost headers after degrade | 4 | 2 | OpenAI invoice / LiteLLM | Degrade and ledger live in one process; invoice-true on-box | Filed [#1885](https://github.com/naveenreddyalka/daari/issues/1885) |
| 194 | OpenAI Decisions GA parity: `input_json`, per-question images, 400-question cap, cached-input billing | 4 | 2 | OpenAI (GA 10-22) | One GA shape, served locally at $0 or forwarded — no client forks | Filed [#1886](https://github.com/naveenreddyalka/daari/issues/1886) |
| 195 | Built-in d3 local decision models + Flint Linux/Windows recipe (Ollama 0.40.9) | 3 | 1 | Ollama / vLLM Semantic Router | Zero-config $0 judge tier on daari's primary runtime | Filed [#1887](https://github.com/naveenreddyalka/daari/issues/1887) |
| 196 | Stream `/v1/audio/speech` relay + Ollama Phonon local TTS recipe | 3 | 2 | OpenAI TTS / Ollama 0.40.9 | Zero-extra-dep local voice behind daari auth/budgets/audit | Filed [#1888](https://github.com/naveenreddyalka/daari/issues/1888) |
| 197 | Panels + alert rules for `service_tier_degraded`, `anthropic_sampling_stripped`, enforced-profiles gauge | 3 | 2 | Datadog / Grafana Cloud packs | Series already on `/metrics`; paging ships in the Helm chart | Filed [#1889](https://github.com/naveenreddyalka/daari/issues/1889) |
| 191 | Fleet-coordinate Responses background job cancel | 4 | 3 | OpenAI background cancel | Redis/lease cancel stops the owning pod | Open ([#1874](https://github.com/naveenreddyalka/daari/issues/1874)) |
| 192 | Ingest Anthropic org enforcement webhooks | 4 | 3 | Anthropic Admin API | Push joins local tenant map + audit | Open ([#1875](https://github.com/naveenreddyalka/daari/issues/1875)) |
| 183–190 | 10-22 waves: streamed cache-write TTL billing; enforcement sync; service-tier degrade; Redis breaker; sampling-strip telemetry; console export/reset; gzip + TTL panels; vLLM floor doc | 3–4 | 1–3 | OpenAI / Anthropic / Kong / LiteLLM | Invoice, blast-radius, HA, day-2 truths | Shipped |
| 136–182 | 10-18 → 10-21 waves: `resultType`; fast-mode; `:cloud` fences; systemone; speed-keyed caches; spend slices; `schema_ok`; events windows; breaker truth; TTL cache billing; user profiles; compromise advisory; version-safe sampling | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Protocol, egress, FinOps, judge ops | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): fleet-share the remaining circuit breakers —
frontier/local pool/MCP egress are still process-local `CircuitBreaker`s
(systemone + key-lockout are the Redis pattern; file after the systemone
share proves out); web-ui enforcement inventory + cache-invalidate form
(HTTP/CLI exist, `app.js` has neither — next console slice); Responses
background **completion webhooks** (distinct from #1874 cancel; reuse the
signed-deliver helper); `migrate --downgrade` + Postgres schema-skew gate on
`/ready` (SQLite `schema_ok` gates, PG is connect-only); Anthropic
`2026-10-21` extra 400s — `document` blocks in assistant messages and
non-empty `citations` in user messages now error (version-keyed strip today
covers sampling only); eMudhra (emSign) CA distrust — certifi 2026.10.23
still ships the roots (notBefore-gated); act when certifi drops them or a
buyer pins `TLS_CA`; Ollama 0.40.10-rc0 Nemotron 3.5 Bolt E4B VLM recipe at
GA; LiteLLM clean post-compromise 1.107 rebuild watchables (ID-JAG/
OAuth-delegate, `agent_access_default_deny`); Portkey WIF upstream creds
(buyer ask); per-user RPD; SCIM + multi-issuer SSO; Prometheus exemplars +
`gen_ai.agent.*`; Kong Skills/A2A passthrough demand.

Verified fine this run — don't re-audit: streamed cache-write TTL billing on
OpenAI + Anthropic shapes and Responses-via-router (`usage_cost_and_cache` →
stream bill); service-tier degrade retries non-stream + stream with
soft_warning (gap is spend/served-tier only, row 193); systemone Redis
breaker fails open with `/ready`/stats/reset wired; enforcement sync has
poll + state + signed webhook + Prom gauge + doctor + HTTP/CLI (webhook
ingest = #1875); sampling strip limited to `temperature`/`top_p`/`top_k`
with soft_warning; web-ui after #1882 has spend `team`/`until`, breaker
reset, events windows, lockouts; Grafana after #1883 has gzip +
cache-write-TTL panels; decisions frontier fallback to `gpt-6-luna` with
input-only billing exists (GA fields = row 194).

---

## Path to enterprise-grade — next 5 milestones

1. **Bill what was served** — served-tier spend + stream cost headers after
   degrade (row 193), finishing the invoice-parity arc of rows 183–185.
2. **Speak Decisions GA** — `input_json`, per-question images, 400-question
   ceiling, cached-input billing (row 194), with d3 as the $0 local judge
   tier (row 195).
3. **Local voice, streamed** — chunked TTS relay + Phonon recipe (row 196).
4. **Package the new truths** — panels and alert rules for degrade/strip/
   enforcement telemetry (row 197).
5. **Drain the HA + tenancy queue** — fleet Responses cancel (191),
   enforcement webhook ingest (192), and the 10-10 console set (62–67).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-23 (bill what was served, speak what went GA)** — Marked rows
  183–190 Shipped (both 10-22 waves merged same-day; drained the stale pm
  PRD PR by taking main — its rows live on as 188–192). Outward: Ollama
  0.40.9 stable (Phonon speech endpoint, d3 decision models, Flint on
  Linux/Windows); OpenAI Decisions GA; eMudhra CA distrust (Portkey
  v2.29.1/Kong trust-store updates; certifi unchanged); semantic-router
  1.0/1.1; LiteLLM floor still 1.106.2. Filed rows 193–197: served-tier
  billing, Decisions GA parity, d3 + Flint recipe, streamed TTS, wave
  observability packaging.

- **2026-10-22 + pm (finish the truths the wave started; console and day-2
  packaging)** — Marked rows 171–182 Shipped. Filed rows 183–187 (streamed
  cache-write billing, enforcement visibility, service-tier degrade,
  fleet-shared breaker, sampling-strip telemetry) and 188–192 (console
  export/reset, Grafana gzip+TTL panels, vLLM floor doc, fleet Responses
  cancel, enforcement webhook ingest). Outward: LiteLLM compromise
  post-mortem (clean floor 1.106.2); Anthropic enforcement_status; OpenAI
  service-tier restrictions; Ollama 0.40.8 GA; vLLM 0.32.0 security wave.

- **2026-10-21 + pm (breaker truth, invoice-true cache billing, user
  profiles; LiteLLM compromise + Anthropic API-version footgun)** — Filed
  rows 173–182; marked 161–172 Shipped/Superseded. Outward: LiteLLM 1.107.0
  compromise (floor 1.106.2); Anthropic API `2026-10-21` removes sampling;
  OpenAI 12h prompt cache; Ollama 0.40.7/0.40.8-rc0.

- **2026-10-20 → 08-28** — Condensed: finish-the-knobs; decisions-upstream
  depth; fast-mode cache truth; `resultType`/egress/billing waves;
  lifecycle/tenancy/DR; LiteLLM 1.104–1.106; Apache 2.0; this PRD's
  creation.
