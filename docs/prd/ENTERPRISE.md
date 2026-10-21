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

## Where daari stands (verified in-tree, 2026-10-21)

**Loop velocity.** The whole 10-20 board drained in under 24 hours again:
morning rows 163–167 and the evening refill's 168–170 all merged (Helm
systemone secret, ISO `reset_at` webhooks, HTTP spend export, breaker state
on stats/doctor, Grafana/alerts for `schema_ok` + breaker, events
`since`/`until`, speed-keyed invalidate, configure first-wave, catalog
`between_tools`). Evening rows 171–172 stay open. The dead evening PRD PR
was drained via take-main (pin rows restored).

**Outward.** LiteLLM cut four coordinated same-day backports — GA floor is
now **1.106.2** (count_tokens Bedrock fallback, P0 batch cost/pricing,
spend fixes); 1.107.0-rc.2 is still the newest prerelease. **Ollama 0.40.7
stable** adds `renderer`/`parser`/`template_source` to show and cancels
remote-model requests on client disconnect; 0.40.8-rc0 debuts Recursive's
Flint 40B-MoE coder. Two fresh API deltas move daari surfaces: **OpenAI
12-hour prompt caching** (10-20, `prompt_cache_options.ttl` 30m/12h with
1.25×/2.5× *total* write rates) and **Anthropic user profiles + org
restrict/ban webhooks** (10-20, `anthropic-user-profile-id` scopes safety
enforcement to one end customer — built for gateways like daari). Portkey
v2.29.0, Kong 2.2.0/3.16.0.1, OpenRouter (Oct 9), vLLM 0.32.0, MCP blog
(Aug 22) all flat. OpenAI models land on Google Cloud Model Garden
(positioning note only).

**Inward theme: close the loop the breaker wave opened, and keep billing
honest.** `daari doctor` checks the breaker **in its own process** — a CLI
run never sees the daemon's open circuit even though `/v1/daari/stats`
exposes it; `/ready` and `/health` ignore a fenced judge hop; the reset
helper is tests-only. The pricing engine cannot bill OpenAI's new TTL-keyed
cache writes (it only knows Anthropic's `1h`). The L6 header allowlist drops
`anthropic-user-profile-id`. The invalidate verb skips team scoping and the
offline CLI path skips audit. The facade's `/api/show` lacks 0.40.7 fields.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 173 | systemone breaker truth: doctor via daemon stats, `/ready` component, admin reset verb | 5 | 2 | Kong/Envoy upstream state | A fenced judge hop must be visible to probes and clearable on the box | Filed [#1842](https://github.com/naveenreddyalka/daari/issues/1842) |
| 174 | Bill OpenAI prompt-cache writes by TTL (30m 1.25× / 12h 2.5× total rates) | 4 | 2 | OpenAI invoice / LiteLLM per-model prices | Ledger, budgets, and the 402 clock must match the provider invoice on-box | Filed [#1843](https://github.com/naveenreddyalka/daari/issues/1843) |
| 175 | Forward `anthropic-user-profile-id` + map daari end users to Anthropic user profiles | 4 | 2 | — (Anthropic shipped it 10-20; no gateway speaks it yet) | The ledger already knows every end user; enforcement blast-radius shrinks to one tenant | Filed [#1844](https://github.com/naveenreddyalka/daari/issues/1844) |
| 176 | Team-scope the cache invalidate verb; audit the offline CLI path | 4 | 2 | — (tenancy depth) | Per-tenant cache control with a local audit trail | Filed [#1845](https://github.com/naveenreddyalka/daari/issues/1845) |
| 177 | Facade `/api/show` parity: Ollama 0.40.7 `renderer`/`parser`/`template_source` | 3 | 1 | Ollama | Ollama-native clients must notice nothing | Filed [#1846](https://github.com/naveenreddyalka/daari/issues/1846) |
| 171 | compare-litellm: cite 1.107.0-rc.2 watchables; keep 1.106 GA floor (now 1.106.2) | 2 | 1 | LiteLLM release notes | Positioning stays honest while RC churns | Open |
| 172 | Prometheus counters for gzip JSON compression | 2 | 1 | Kong/Envoy compression metrics | Same-box scrape shows Accept-Encoding payoff | Open |
| 161–170 | 10-19 eve + 10-20 waves: budget-webhook ISO `reset_at` + model-cap crossings; gateway systemone pin; Helm `systemone.apiKeySecret`; HTTP spend export; breaker state surfaces; Grafana `schema_ok`/breaker; events `since`/`until`; speed-keyed invalidate; configure first-wave; catalog `between_tools` | 2–4 | 1–3 | LiteLLM / Portkey / Kong | FinOps, judge ops, and catalog honesty on-box | Shipped |
| 150–160 | 10-19 waves: speed-keyed L0/L1 caches; systemone base_url/auth/breaker/Helm/doctor/executor labels; spend `--model`/`--usage-speed` + Grafana cloud/fast panels; `schema_ok` scrape + banner; events console filters | 2–4 | 1–3 | LiteLLM / vLLM / Portkey | Cache truth, governed judge upstream, FinOps slices on-box | Shipped |
| 136–149 | 10-18 waves: `resultType` everywhere; fast-mode stream degrade/headers/billing; `:cloud` fences + catalog markers; replay/ledger honesty; configurable systemone upstream; 1.106 GA floor | 2–5 | 1–3 | Claude Code / Anthropic / LiteLLM / vLLM | Protocol, egress, and billing truth on-box | Shipped |
| 131 | Ollama `:cloud` counts as remote egress for `no_frontier` / PII scrub / region fences | 5 | 2 | Portkey egress fences | "Local-only means local-only" is the core promise | Shipped |
| 117–130 | 10-16/10-17 waves: modality 410; Opus fast billing; scoped reads; lockout unlock; Helm consistent backup; client recipes; catalog/doctor/ready honesty | 2–5 | 1–3 | — / Ollama / LiteLLM | Lifecycle, tenancy, DR, onboarding on-box | Shipped |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 107–116 | 10-15 waves: retired-410 facades; team-scoped reads; consistent backup; TLS doctor; webhook secret rotation; traceresponse; events HTTP; key lockout; Grafana errors-by-status; chatgpt-desktop | 3–5 | 1–4 | — / Kong / LiteLLM 1.107-dev | Lifecycle + tenancy + DR + trace round-trip on-box | Shipped |
| 90/91/78 | Member budget webhooks; DEC/SYS bench docs; LiteLLM 1.106 compare note | 2–3 | 1–3 | LiteLLM 1.105/1.106 | Runaway-agent alerts + benchmarking honesty | Shipped |
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
| 8 | Full DCR; A2A (Kong 3.16.0.1 speaks v1.0); Realtime/WS (incl. GPT-Live Decisions); stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): Helm `systemone.apiKeySecret`; budget
webhooks with ISO `reset_at` + `model_max_budget` crossings; HTTP spend
export with `model`/`usage_speed` filters (analyst-gated, team-scoped,
paginated, audited); breaker state on stats/doctor/console; Grafana +
PrometheusRule for `daari_schema_ok` and the breaker series; events
`since`/`until` on store/API/console/CLI; L0/L1 invalidate by `speed`;
configure first-wave registry parity (pin test exists); catalog
`between_tools` + local-tier degrade via `dropped_params` + gateway event.

Watch rows (do not file yet): Anthropic org restrict/ban webhooks ingest →
auto-block the mapped daari end user (file after row 175 ships); spend
export panel on the web console (`spend/export` is HTTP/CLI-only — fold
into the next console sweep); `record_soft_warning` / Prom series when
local paths strip `thinking.between_tools` (dropped_params-only today);
shared multi-replica breaker store (each pod fences independently at
`replicaCount≥2` — fleet demand); `doctor-health.md` row for the
`systemone_breaker` tip (fold into row 173); LiteLLM 1.107 GA watchables
(ID-JAG/OAuth-delegate DCR bridge, `agent_access_default_deny`, count
endpoints source-API errors); Ollama Flint recipe + `ollama launch` parity
(0.40.8 still rc); OpenAI `chat-latest` alias + Agents ultrafast
`service_tier` passthrough; systemone multi-upstream / opt-in Ollama
fallback; cursor-agent CLI configure; `migrate --downgrade`; Responses
background completion webhooks + wider `include` allowlist; per-user
request-count RPD; SCIM + multi-issuer SSO; Prometheus exemplars +
`gen_ai.agent.*` spans; Kong `ai-proxy-advanced` passthrough route type +
Skills API forwards (re-check on demand); OpenAI-on-Google-Cloud + Anthropic
Compliance user-preferences export (non-goals).

Verified fine this run — don't re-audit: spend export enforces analyst role
+ `_admin_team_scope` + `_clamp_page` + audit; `model_max_budget` webhook
crossings reuse the Redis SET-NX dedupe + HMAC signing of the shared
alerter; events console exposes `since`/`until` and prune honors
`request_log_days`; `CONFIGURE_CLIENTS` ⊆ registry pinned by
`test_configure_cli.py`; HTTP invalidate is admin-gated + audited (gap is
scoping, row 176); the breaker self-recovers via half-open probes (gap is
visibility/reset, row 173); `prompt_cache_options` forwards verbatim on L6
(gap is billing, row 174).

---

## Path to enterprise-grade — next 5 milestones

1. **Make the fenced judge hop visible and clearable** — doctor reads the
   daemon's breaker state, `/ready` reports it, admins can reset it
   (row 173).
2. **Bill cache writes like the invoice does** — TTL-keyed OpenAI write
   rates so budgets and chargeback match provider billing (row 174).
3. **Shrink enforcement blast radius to one tenant** — end-user →
   `anthropic-user-profile-id` mapping on the Anthropic hop (row 175),
   then webhook ingest (watch).
4. **Finish invalidate tenancy** — team-pinned admins cannot wipe other
   tenants; offline CLI leaves an audit row (row 176).
5. **Stay indistinguishable from real Ollama** — 0.40.7 `show` field parity
   on the facade (row 177), plus the P3 leftovers (rows 171–172).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-21 (breaker truth, invoice-true cache billing, user-profile
  blast radius)** — Marked rows 161–170 Shipped (the whole 10-20 board
  merged in <24h); drained the dead 10-20 evening PRD PR via take-main and
  folded its rows in (171–172 stay open). Filed rows 173–177: breaker
  doctor/ready/reset truth, OpenAI prompt-cache TTL write billing
  (10-20 API change: 30m 1.25× / 12h 2.5× total write rates),
  `anthropic-user-profile-id` forwarding + end-user mapping (10-20 Anthropic
  launch for gateways/resellers), invalidate team scoping + offline CLI
  audit, and facade `show` parity with Ollama 0.40.7. Outward: LiteLLM GA
  floor 1.106.2 via four same-day backports; Ollama 0.40.7 stable
  (`renderer`/`parser`/`template_source`, remote cancel-on-disconnect) +
  0.40.8-rc0 Flint; Portkey/Kong/OpenRouter/vLLM/MCP flat; OpenAI models
  coming to Google Cloud Model Garden.

- **2026-10-20 (finish the knobs the wave shipped + evening speed-keyed
  ops)** — Filed rows 163–167 (Helm `systemone.apiKeySecret`, HTTP spend
  export, breaker state surfaces, Grafana/alerts for `schema_ok` + breaker,
  events `since`/`until`) and evening rows 168–172 (speed-keyed invalidate,
  configure first-wave, catalog `between_tools`, compare-litellm RC note,
  gzip Prom counters). Outward: LiteLLM 1.106.0 GA floor; 1.107.0-rc.2 MCP
  ID-JAG/OAuth-delegate + count_tokens stacks on watch; Anthropic
  `capabilities.thinking.types.between_tools` (10-15 Models API field).

- **2026-10-19 (two scans: decisions-upstream depth + fast-mode cache
  truth; evening cache alias + console honesty)** — Marked rows 136–149
  Shipped. Filed rows 150–162 across the day: L0/L1 `speed` cache keys,
  Helm/NetworkPolicy + Bearer auth + circuit breaker + pooled classifier
  for the systemone upstream, spend export/Grafana slices, `schema_ok`
  gauge + banner, events console filters, budget-webhook ISO `reset_at`,
  gateway-flow systemone pin. Kong Gateway 3.16.0.1 (`ai-a2a-proxy` A2A
  v1.0, byte-preserving `ai-proxy-advanced` forwards).

- **2026-10-18 → 08-28** — Condensed: three 10-18 scans (1.106 GA floor,
  replay/count/ledger honesty, stream-path fast mode + egress truth + vLLM
  0.32); three 10-17 scans (egress truth, stream billing, ops surfaces;
  protocol cache hints + Ollama cloud/quant honesty; client recipes +
  upgrade skew); edge-depth lifecycle doors + tenancy totals + fast mode +
  deploy defaults; post-wave lifecycle/tenancy/DR/TLS depth; overnight-wave
  parity; day-2 operations + observability packaging; concurrency +
  decision-guardrail depth; control-plane honesty + MCP server rpm; export
  honesty + doctor ACL; team DR + console lifecycle; RBAC floors +
  decisions agility; key/end-user lifecycle; admin-plane honesty;
  Decisions/OAuth/multi-agent; governance parity; LiteLLM 1.104; Apache
  2.0; this PRD's creation.
