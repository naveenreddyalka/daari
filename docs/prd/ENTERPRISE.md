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

## Where daari stands (verified in-tree, 2026-11-07 pm)

**Loop velocity.** Since the 11-07 morning PRD: virtual-model SLO demotion
counters (#2166 / row 307) and opt-in OTel request tags (#2168 / row 308)
Shipped. Morning Auto Router / PG-blip filings (#2162–#2165 / rows 326–329)
remain open. The dead 11-06 pm Actions PRD (#2157) already drained via
take-main earlier today.

**Outward.** Landscape mostly flat vs the morning scan. **LiteLLM v1.108.2
LTS** (11-06) is still the live patch floor while compare copy pins
**1.108.0** — convert the docs promote as row 331; **1.110.0-dev.1**
(11-07) stays Watch (provider-reported `usage.cost`, tenant session
affinity, Lens-split Helm). **OpenRouter Auto + Auto Code** (11-06) were
already converted for effort/cost levers; compare-openrouter still never
names them — row 332. Portkey v2.33.1, Ollama **0.40.15**, vLLM
`v0.33.0rc3`-named-0.33.0, Kong 3.9.4, MCP rev 2026-07-28, OpenAI /
Anthropic changelogs — all flat since morning.

**Inward theme: observe and compare what just shipped.** SLO demotion and
request-tag OTel need same-box Grafana / config ownership; hermetic fence
for the afternoon wave; honest LiteLLM LTS + OpenRouter Auto compare copy.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 330 | Grafana panels for `daari_virtual_model_slo_demotion_total` | 2 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box scrape for the SLO dial just shipped | Filed [#2169](https://github.com/naveenreddyalka/daari/issues/2169) |
| 331 | Promote compare-litellm floor to LiteLLM 1.108.2 LTS; watch 1.110-dev | 2 | 1 | LiteLLM release notes | Honest LTS patch floor without a runtime dep | Filed [#2170](https://github.com/naveenreddyalka/daari/issues/2170) |
| 332 | compare-openrouter: Auto + Auto Code local-first positioning | 3 | 1 | OpenRouter Auto / Auto Code (11-06) | On-box virtual-models + signal_overrides vs hosted pick | Filed [#2171](https://github.com/naveenreddyalka/daari/issues/2171) |
| 333 | Config ownership + PATCH for `observability.otel_include_request_tags` | 3 | 1 | Portkey Complete Logs / LiteLLM tag dashboards | Hot-edit tag export on operator-owned OTel | Filed [#2172](https://github.com/naveenreddyalka/daari/issues/2172) |
| 334 | Integration fence for the 11-07 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: SLO demotion Prom + OTel request tags | Filed [#2173](https://github.com/naveenreddyalka/daari/issues/2173) |
| 326 | `reasoning_effort` lever on signal_overrides (auto effort pick) | 4 | 2 | OpenRouter Auto/Auto Code (11-06) | Effort picked by on-box signals; payload never leaves the box | Filed [#2162](https://github.com/naveenreddyalka/daari/issues/2162) |
| 327 | Serve last-known-good virtual keys across Postgres blips | 4 | 2 | LiteLLM 1.108.2 LTS auth fix | Local tiers keep serving through a control-plane restart | Filed [#2163](https://github.com/naveenreddyalka/daari/issues/2163) |
| 328 | Cost-aware virtual-model selection mode | 3 | 2 | OpenRouter Auto Router live-pricing factor | Zero-cost local tiers sort first from the arithmetic | Filed [#2164](https://github.com/naveenreddyalka/daari/issues/2164) |
| 329 | Integration fence for the 11-06/11-07 overnight wave | 2 | 2 | — (testability) | Hermetic proof: Codex PAT, priority Prom, tier inventory | Filed [#2165](https://github.com/naveenreddyalka/daari/issues/2165) |
| 321 | Grafana panels for `service_tier_not_allowed` deny + degrade | 2 | 1 | OpenAI Platform / LiteLLM Admin spend | Same-box scrape for the dial counters just shipped | Filed [#2152](https://github.com/naveenreddyalka/daari/issues/2152) |
| 322 | Map W3C `baggage` into request tags (opt-in) | 3 | 2 | LiteLLM 1.109.0-rc.1 baggage→spend tags | Mesh identity steers local signal_overrides on-box | Filed [#2153](https://github.com/naveenreddyalka/daari/issues/2153) |
| 323 | Admin + web-ui surface for `allowed_ips` | 3 | 1 | Anthropic Console org IP allowlist | Per-key/team lists editable next to other dials | Filed [#2154](https://github.com/naveenreddyalka/daari/issues/2154) |
| 324 | OpenAI AU/IN/JP residency pins + 1.10× billing | 3 | 2 | OpenAI data-residency endpoints (11-05) | Honest on-box pin + cost_usd; local tiers unaffected | Filed [#2155](https://github.com/naveenreddyalka/daari/issues/2155) |
| 325 | Integration fence for the 11-06 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: refusals + service-tier metrics | Filed [#2156](https://github.com/naveenreddyalka/daari/issues/2156) |
| 316 | Per-key/team client IP allowlist (CIDR) on virtual-key auth | 4 | 2 | Anthropic Console org IP allowlist (11-05 beta) | Per-key/team blast-radius control on-box, local tiers included | Filed [#2144](https://github.com/naveenreddyalka/daari/issues/2144) |
| 317 | Revoke every SSO-minted key for a subject (offboarding kill switch) | 4 | 2 | Anthropic Admin API sign-out-everywhere (11-05 beta) | One on-box call kills keys + team grants, no IdP webhook lag | Filed [#2145](https://github.com/naveenreddyalka/daari/issues/2145) |
| 318 | AutoTrust (`autotrust-jev`) local decision-model family | 3 | 2 | Ollama 0.40.15 / Portkey Clef decisions | Decisions stay on-box with budgets, guardrails, audit | Filed [#2146](https://github.com/naveenreddyalka/daari/issues/2146) |
| 319 | MiMo V2.6 L4 code/agent recipe | 3 | 1 | Ollama 0.40.15 | Agent loops on a 9B local tier, frontier only on escalation | Filed [#2147](https://github.com/naveenreddyalka/daari/issues/2147) |
| 320 | Integration fence for the 11-05/11-06 overnight wave | 2 | 2 | — (testability) | Hermetic proof: temp omit, rate kinds, show limits, rotation | Filed [#2148](https://github.com/naveenreddyalka/daari/issues/2148) |
| 311 | Stats/Prom for Anthropic message-threads create/continue/soft-ignore | 3 | 1 | Anthropic Claude Platform / Claude Code | Chart L6 thread pressure vs local fail-closed on-box | Filed [#2133](https://github.com/naveenreddyalka/daari/issues/2133) |
| 312 | Opt-in `user_agent` on OTel GenAI spans | 3 | 1 | Portkey v2.33.0 Complete Logs | IDE/agent attribution in operator-owned OTel | Filed [#2134](https://github.com/naveenreddyalka/daari/issues/2134) |
| 313 | Admin + web-ui surface for `virtual_model_latency_slo_ms` | 3 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box console for the SLO dial selection already uses | Filed [#2135](https://github.com/naveenreddyalka/daari/issues/2135) |
| 314 | Opt-in omit requester `client_ip` from enterprise audit | 3 | 2 | LiteLLM 1.108.0 `disable_requester_ip_address_logging` | Privacy dial on operator-owned audit disk | Filed [#2136](https://github.com/naveenreddyalka/daari/issues/2136) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 307, 308 | SLO demotion Prom/stats; opt-in request tags on OTel GenAI spans | 3 | 1 | OpenRouter / Portkey Complete Logs | Operator-owned traces next to local-tier cost attrs | Shipped (#2166, #2168) |
| 309 | Config ownership + PATCH for `routing.virtual_model_latency_slo_ms` | 3 | 1 | LiteLLM / OpenRouter control planes | Hot-edit SLO ms without restart | Filed [#2125](https://github.com/naveenreddyalka/daari/issues/2125) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: prior overnight dials | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 299, 301–304, 306 | Refusal parts; service-tier Prom + console; Codex PAT L6; priority Prom; 1.108.0 LTS floor | 2–3 | 1–2 | Ollama / OpenAI / Portkey / LiteLLM | Governance + honesty on the same-box scrape and console | Shipped (#2150–#2151, #2158–#2161) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 294, 296–298 | Rate-limit kind split; temperature omit; batches rotation; `/api/show` limits | 3–4 | 1–2 | LiteLLM / Ollama 0.40.14 | Byte-equivalence + signed push channels | Shipped (#2139–#2140, #2142–#2143) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 281–293 | LTS compare; offline PATCH; batch webhook; tags; OTel cost; latency SLO; vLLM notes; MCP oauth; threads; TPD UI; selection Grafana | 2–4 | 1–3 | LiteLLM / Portkey / OpenRouter / Anthropic | Operator-owned traces, honest tiers, same-box console | Shipped (#2116–#2121, #2128–#2132) |
| 295 | Integration fence for the 11-02 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: TPD + OpenRouter compare pin | Filed [#2097](https://github.com/naveenreddyalka/daari/issues/2097) |
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | Shipped | Shipped |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | Shipped | Shipped |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | Shipped | Shipped |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | Shipped | Shipped |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | Shipped | Shipped |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | Shipped | Shipped |
| 279 | Prometheus counter for offline-mode refused egress | 2 | 1 | — (ops honesty) | Prove the air gap held from the scrape | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072) |
| 285 | Doctor tip: offline_mode on + live frontier L6 creds | 2 | 1 | — (ops honesty) | Same-box warning before the 403 storm | Filed [#2079](https://github.com/naveenreddyalka/daari/issues/2079) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): coding-router recipe — an Auto Code twin
combining virtual_models + `category=code` signal rules + SLO + the effort
lever (file after rows 326/328 land); LiteLLM `1.110.0-dev` feature
backlog beyond the compare watch (provider-reported `usage.cost` billing,
tenant-scoped session affinity, Lens-split Helm — hold for a stable cut);
Portkey v2.33 Anthropic `auto_caching` (revisit only if top-level
`cache_control` diverges); Portkey MCP access policies (Prisma AIRS-only);
Portkey OTel workspace name; Bedrock metadata map; LiteLLM OpenAI Live
`/v1/live/sessions` + Azure PTU split + M365 Copilot + `gpt-live-1`
outbound SIP (Realtime/WS family); AutoTrust beyond Apple silicon;
`gpt-6-cyber` (Daybreak restricted); gpt-image-2.6 sunburst/flare catalog;
Agents API `auto_review`; Anthropic text watermark (metric-only);
minute-grain spend buckets; fleet Redis EWMA; MCP SEP-3398 (~March 2027);
OpenAI org external key management; Anthropic Compliance API; Models API
`between_tools` Sonnet-5.5-only; `gpt-6-rosalind`; Claude Code `groups` /
`guardrail_trace`; OpenRouter private-provider CRUD + S3/IAM; LiteLLM
Admin Chat UI / Lens; llama.cpp `/v1/realtime` + `POST /tts` + deferred
tools; Portkey claim-based JWT / WIF; OpenAI `/agents/automations`; Prisma
AIRS Agent Identity; Claude-on-GCP IAM (new dep — human); Anthropic hosted
skills; Claude Tag beta; Open Responses WS; Anthropic OTel export beta;
Prom exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer
SSO; Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi
emSign; Ollama d1 Linux/Windows GA; local message-thread analogue (prefix
store on L3–L5 — only after explicit agent-loop ask); OpenAI CA/SG/KR/UAE/UK
residency labels beyond au/in/jp (expand only when operators ask).

Verified fine this run — don't re-audit: rows 307/308 counters and OTel
flag are on main (`daari_virtual_model_slo_demotion_total`,
`observability.otel_include_request_tags`); Grafana still has **no** SLO
demotion panel (dashboard search clean); compare-litellm still asserts
**1.108.0** floor; compare-openrouter never mentions Auto / Auto Code;
`otel_include_request_tags` absent from config ownership; Portkey v2.33.1
floor holds; Ollama top stable **0.40.15**; MCP spec rev 2026-07-28
unchanged; LiteLLM 1.110.0-dev.1 is pre-release only.

---

## Path to enterprise-grade — next 5 milestones

1. **Contain the leaked key** — per-key/team IP allowlist (316) + console
   (323); revoke-subject offboarding (317); audit IP omit (314).
2. **Route like the new Auto Router** — effort lever (326); cost-aware
   selection (328); then the coding-router recipe (watch); SLO PATCH
   (309) + console (313); Grafana for SLO demotions (330).
3. **Survive the control-plane blip** — last-known-good auth grace (327);
   offline Prom (279) + doctor (285); hot-reload (6).
4. **Observe + compare what shipped** — service-tier Grafana (321); SLO
   demotion Grafana (330); OTel tags PATCH (333); thread counters (311);
   UA spans (312); failover panels (274); LiteLLM 1.108.2 + OpenRouter
   Auto compare (331–332); afternoon fence (334); then rows 62–67.
5. **Residency + local runtime at the current bar** — AU/IN/JP pins (324);
   baggage→tags (322); AutoTrust (318); MiMo (319); fences (300, 305, 310,
   315, 320, 325, 329).

---

## Changelog

- **2026-11-07 pm (observe + compare the afternoon wave)** — Marked rows
  307–308 Shipped (SLO demotion Prom/stats; OTel request tags). Outward:
  LiteLLM 1.108.2 still ahead of compare floor; 1.110.0-dev.1 → Watch;
  OpenRouter Auto/Auto Code still missing from compare-openrouter;
  Portkey/Ollama/vLLM/Kong/MCP/OpenAI/Anthropic flat. Filed rows 330–334:
  SLO demotion Grafana, compare 1.108.2 + 1.110-dev watch, OpenRouter Auto
  compare, OTel tags config ownership, afternoon fence. Kept pinned
  shipped rows 19–28. Issue #2141 still needs human close.

- **2026-11-07 (route like Auto Router; survive the PG blip)** — Marked
  rows 299, 301–304, 306 Shipped (#2150–#2151, #2158–#2161). Adopted the
  dead 11-06 pm Actions PR's rows as 321–325. Outward: OpenRouter Auto +
  Auto Code → rows 326/328; LiteLLM 1.108.2 auth-outage fix → row 327.
  Filed rows 326–329.

- **2026-11-06 + 11-06 pm (leaked-key blast radius; Ollama 0.40.15 GA;
  observe/residency tail)** — Marked rows 294, 296–298 Shipped. Filed
  rows 316–320 and 321–325. Drained dead Actions PRD PR #2127 (stall
  issue #2141 needs human close).

- **2026-11-05 (TTFT/SLO observe tail; Portkey 2.33 UA; LiteLLM IP omit)** —
  Marked rows 281–284, 286–289, 291–293 Shipped. Filed rows 311–315.

- **2026-11-03 pm → 10-28** — Condensed: governance console / Codex PAT /
  admission Prom; Ollama 0.40.14 parity; message-threads / TPD / selection
  Grafana; trace cost / latency SLO / vLLM / MCP cc; LTS / air-gap / batch
  default / request tags; through Apache 2.0 and this PRD's creation.
