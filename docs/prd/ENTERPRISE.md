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

## Where daari stands (verified in-tree, 2026-10-22)

**Loop velocity.** The entire 10-21 wave is merged: rows 171–182 all closed in
under a day (breaker truth, TTL cache billing, user profiles, invalidate
tenancy, facade `show`, console export, `between_tools` telemetry, gzip Prom,
Flint recipe, compromise advisory, version-safe sampling). The remaining
open backlog is the 10-10 tenancy/console set, all `agent:working`.

**Outward.** LiteLLM published its 1.107.0 compromise post-mortem (contained;
clean floor **1.106.2**, digest-pinned images) — daari's advisory shipped.
Anthropic's second 10-21 drop added **`enforcement_status` /
`enforcement_actions` on user profiles** + list filter (SDK 2.1.0) — the
missing half of the blast-radius story daari started with user-profile
forwarding. OpenAI 10-21 added **org/project service-tier restrictions**
(restricted tiers now error). Ollama 0.40.8 went GA (Flint, recipe shipped).
vLLM 0.32.0 closed 9 security advisories (incl. one-request engine-crash
DoS). Kong flat since 2.2; Portkey v2.20.0 (MCP guardrails, WIF) watch;
MCP spec flat.

**Inward theme: finish the truths the wave started.** Streamed L6 responses
drop `cache_write_tokens` from bill meta/ledger, so TTL-rated cache writes
underbill exactly where #1857 promised invoice parity. The systemone breaker
store is a process-local dict — in a fleet, `/ready`, stats, and admin reset
are per-pod fiction. The 2026-10-21 sampling strip has `dropped_params` but
no soft_warning/Prom (unlike `between_tools`). No degrade path when OpenAI
rejects a restricted `service_tier` (the Anthropic fast-degrade pattern
exists to mirror). Zero enforcement visibility for mapped end users.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 183 | Bill cache-write tokens + TTL rates on streamed L6 responses | 4 | 2 | OpenAI invoice / LiteLLM | Stream frames parsed on-box; ledger lives next to them | Filed [#1865](https://github.com/naveenreddyalka/daari/issues/1865) |
| 184 | Surface Anthropic user-profile `enforcement_status` for mapped end users | 4 | 3 | Anthropic console | Enforcement joined to local tenant inventory, doctor, Prom, webhooks | Filed [#1866](https://github.com/naveenreddyalka/daari/issues/1866) |
| 185 | Degrade OpenAI `service_tier` on org/project restriction errors | 4 | 2 | — (OpenAI 10-21) | Keep requests alive under org policy; on-box warning trail | Filed [#1867](https://github.com/naveenreddyalka/daari/issues/1867) |
| 186 | Fleet-shared systemone breaker state + reset via Redis | 4 | 3 | Kong/Envoy shared upstream health | Same Redis as L0/L1; single-box stays zero-dep | Filed [#1868](https://github.com/naveenreddyalka/daari/issues/1868) |
| 187 | soft_warning + Prom when `2026-10-21` strips sampling params | 3 | 1 | LiteLLM compact telemetry | On-box count of clients still sending dead knobs | Filed [#1869](https://github.com/naveenreddyalka/daari/issues/1869) |
| 171–182 | 10-20/10-21 waves: breaker truth; TTL cache billing; user profiles; invalidate tenancy; facade `show`; console export; `between_tools` + gzip telemetry; Flint; LiteLLM compromise advisory; version-safe sampling (171 superseded) | 2–5 | 1–3 | LiteLLM / Ollama / Anthropic | Billing truth, tenancy, catalog honesty | Shipped |
| 136–170 | 10-18 → 10-20 waves: `resultType`; fast-mode; `:cloud` fences; systemone auth/breaker/Helm; speed-keyed caches; spend slices; `schema_ok`; events windows | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Protocol, egress, FinOps, judge ops | Shipped |
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

Watch rows (do not file yet): Responses background jobs are process-local
(`_BACKGROUND_JOBS` dict; cancel/poll cross-pod races — file after the
current console wave drains); console parity polish — spend-export `team`/
`until` filters + breaker-reset button (status renders, no action);
Grafana panels for cache-write TTL premium + gzip counters;
vllm-local-tier.md security floor ≥0.32.0 (9 advisories);
Anthropic org restrict/ban **webhook ingest** (beta `webhooks-2026-10-07`,
after row 184 polling lands); LiteLLM post-quarantine clean 1.107 rebuild
watchables (ID-JAG/OAuth-delegate, `agent_access_default_deny`) once a
verified non-compromised GA exists; Portkey 2.20 WIF for OpenAI/Anthropic
(short-lived upstream creds — buyer ask); Ollama Flint GPU beyond Mac;
systemone multi-upstream; `migrate --downgrade`; Responses background
completion webhooks; per-user RPD; SCIM + multi-issuer SSO; Prometheus
exemplars + `gen_ai.agent.*`; Kong Skills/passthrough demand.

Verified fine this run — don't re-audit: `anthropic-version` ingress →
egress passthrough (#455) + version-keyed sampling strip; web-ui spend
export carries `since`/`format`/`model`/`usage_speed` (gap is `team`/`until`
only); doctor-health.md has the `systemone_breaker` tip row; facade
`/api/chat`+`/api/generate` accept `think` + `format` (incl. schema);
spend-export HTTP test combines team+model+speed; breaker reset authz
tested (non-admin 403); CORS defaults closed; Helm image digest pin +
cosign docs exist; catalog advertises nothing version-wrong after #1856.

---

## Path to enterprise-grade — next 5 milestones

1. **Invoice parity on streams** — cache-write tokens + TTL rates on the
   streaming path, where most production traffic lives (row 183).
2. **Close the blast-radius loop** — see when Anthropic restricts or bans a
   mapped tenant, on-box (row 184).
3. **Fleet-true breaker ops** — shared state + fleet-wide reset so `/ready`
   and doctor say the same thing on every pod (row 186).
4. **Survive org tier policy** — degrade restricted `service_tier` instead
   of failing requests (row 185), with the strip telemetry to plan client
   migrations (row 187).
5. **Drain the tenancy/console wave in flight** — end-user inventory,
   guardrail profiles, paged reports/console (rows 62–67, all in progress).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-22 (finish the truths the wave started)** — Marked rows 171–182
  Shipped (whole 10-21 wave merged in under a day). Outward: LiteLLM
  compromise post-mortem (clean floor 1.106.2, digest pinning); Anthropic
  user-profile `enforcement_status` + filter (SDK 2.1.0); OpenAI org/project
  service-tier restrictions; Ollama 0.40.8 GA; vLLM 0.32.0 security wave.
  Filed rows 183–187: streamed cache-write billing, enforcement visibility,
  service-tier degrade, fleet-shared breaker, sampling-strip telemetry.

- **2026-10-21 + pm (breaker truth, invoice-true cache billing, user
  profiles; LiteLLM compromise + Anthropic API-version footgun)** — Filed
  rows 173–182; marked 161–172 Shipped/Superseded. Outward: LiteLLM 1.107.0
  compromise (floor 1.106.2); Anthropic API `2026-10-21` removes sampling;
  OpenAI 12h prompt cache; Ollama 0.40.7/0.40.8-rc0.

- **2026-10-20 (finish the knobs + evening speed-keyed ops)** — Filed rows
  163–172. Outward: LiteLLM 1.106.0 GA; Anthropic
  `thinking.types.between_tools`.

- **2026-10-19 → 08-28** — Condensed: decisions-upstream depth; fast-mode
  cache truth; `resultType`/egress/billing waves; lifecycle/tenancy/DR;
  LiteLLM 1.104–1.106; Apache 2.0; this PRD's creation.
