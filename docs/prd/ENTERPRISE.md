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

## Where daari stands (verified in-tree, 2026-11-06 pm)

**Loop velocity.** Afternoon since the morning PRD: service-tier allowlist
stats/Prom (#2151 / #2110) and Responses refusal-part preservation (#2150 /
#2105) Shipped. Morning rows 316–320 (IP allowlist, revoke-subject, AutoTrust,
MiMo, overnight fence) still open. Overnight wave 294, 296–298 remains Shipped.

**Outward.** Competitive floor mostly flat vs morning: **Ollama 0.40.15** GA,
**LiteLLM v1.108.1** LTS patch (promote compare floor via open compare issue;
still **1.109.0-rc.1** watch — baggage→spend-tags converts this run),
**Portkey v2.33.1** fixes-only. **OpenAI** AU/IN/JP data-residency endpoints
(`au`/`in`/`jp.api.openai.com`, openai-node 2026-11-05) convert — daari
`_REGIONAL_PROCESSING_PINS` is still us/eu-only. gpt-6-cyber / gpt-image-2.6 /
gpt-live-1 SIP / Agents `auto_review` stay Watch. Anthropic IP-allowlist +
sign-out-everywhere already filed morning. vLLM `v0.33.0rc3`-named-0.33.0;
Kong 3.9.4; OpenRouter docs still flaky (HTML shell, no usable changelog body).

**Inward theme: observe what shipped + honor new residency/mesh dials.**
Counters without Grafana, CLI governance without console, us/eu-only billing
when OpenAI added three regions, and LiteLLM baggage tags with no local twin.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 321 | Grafana panels for `service_tier_not_allowed` deny + degrade | 2 | 1 | OpenAI Platform / LiteLLM Admin spend | Same-box scrape for the dial counters just shipped | Filed [#2152](https://github.com/naveenreddyalka/daari/issues/2152) |
| 322 | Map W3C `baggage` into request tags (opt-in) | 3 | 2 | LiteLLM 1.109.0-rc.1 baggage→spend tags | Mesh identity steers local signal_overrides on-box | Filed [#2153](https://github.com/naveenreddyalka/daari/issues/2153) |
| 323 | Admin + web-ui surface for `allowed_ips` | 3 | 1 | Anthropic Console org IP allowlist | Per-key/team lists editable next to other dials | Filed [#2154](https://github.com/naveenreddyalka/daari/issues/2154) |
| 324 | OpenAI AU/IN/JP residency pins + 1.10× billing | 3 | 2 | OpenAI data-residency endpoints (11-05) | Honest on-box pin + cost_usd; local tiers unaffected | Filed [#2155](https://github.com/naveenreddyalka/daari/issues/2155) |
| 325 | Integration fence for the 11-06 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: refusals + service-tier metrics | Filed [#2156](https://github.com/naveenreddyalka/daari/issues/2156) |
| 316 | Per-key/team client IP allowlist (CIDR) on virtual-key auth | 4 | 2 | Anthropic Console org IP allowlist (11-05 beta) | Per-key/team blast-radius control on-box | Filed [#2144](https://github.com/naveenreddyalka/daari/issues/2144) |
| 317 | Revoke every SSO-minted key for a subject (offboarding kill switch) | 4 | 2 | Anthropic Admin API sign-out-everywhere (11-05 beta) | One on-box call kills keys + team grants | Filed [#2145](https://github.com/naveenreddyalka/daari/issues/2145) |
| 318 | AutoTrust (`autotrust-jev`) local decision-model family | 3 | 2 | Ollama 0.40.15 / Portkey Clef decisions | Decisions stay on-box with budgets, guardrails, audit | Filed [#2146](https://github.com/naveenreddyalka/daari/issues/2146) |
| 319 | MiMo V2.6 L4 code/agent recipe | 3 | 1 | Ollama 0.40.15 | Agent loops on a 9B local tier | Filed [#2147](https://github.com/naveenreddyalka/daari/issues/2147) |
| 320 | Integration fence for the 11-05/11-06 overnight wave | 2 | 2 | — (testability) | Hermetic proof: temp omit, rate kinds, show limits, rotation | Filed [#2148](https://github.com/naveenreddyalka/daari/issues/2148) |
| 311 | Stats/Prom for Anthropic message-threads create/continue/soft-ignore | 3 | 1 | Anthropic Claude Platform / Claude Code | Chart L6 thread pressure vs local fail-closed | Filed [#2133](https://github.com/naveenreddyalka/daari/issues/2133) |
| 312 | Opt-in `user_agent` on OTel GenAI spans | 3 | 1 | Portkey v2.33.0 Complete Logs | IDE/agent attribution in operator-owned OTel | Filed [#2134](https://github.com/naveenreddyalka/daari/issues/2134) |
| 313 | Admin + web-ui surface for `virtual_model_latency_slo_ms` | 3 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box console for the SLO dial | Filed [#2135](https://github.com/naveenreddyalka/daari/issues/2135) |
| 314 | Opt-in omit requester `client_ip` from enterprise audit | 3 | 2 | LiteLLM 1.108.0 `disable_requester_ip_address_logging` | Privacy dial on operator-owned audit disk | Filed [#2136](https://github.com/naveenreddyalka/daari/issues/2136) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 306 | compare-litellm: promote GA floor to 1.108.x LTS (land as **1.108.1**) | 2 | 1 | LiteLLM LTS / release notes | Honest support window; no proxy pin | Filed [#2122](https://github.com/naveenreddyalka/daari/issues/2122) |
| 307 | Prom/stats counters for virtual-model latency SLO demotions | 3 | 1 | OpenRouter performance router analytics | SLO pressure from on-box EWMA | Filed [#2123](https://github.com/naveenreddyalka/daari/issues/2123) |
| 308 | Opt-in request tags on OTel GenAI spans | 3 | 1 | Portkey Complete Logs / LiteLLM tag dashboards | Workload tags next to local-tier cost attrs | Filed [#2124](https://github.com/naveenreddyalka/daari/issues/2124) |
| 309 | Config ownership + PATCH for `routing.virtual_model_latency_slo_ms` | 3 | 1 | LiteLLM / OpenRouter control planes | Hot-edit SLO ms without restart | Filed [#2125](https://github.com/naveenreddyalka/daari/issues/2125) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: prior overnight dials | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 301 | Stats/Prom counters for `service_tier_not_allowed` deny + degrade | 3 | 1 | OpenAI Platform / LiteLLM spend | Governance cliffs on the same-box scrape | Shipped (#2151) |
| 302 | Admin + web-ui surface for `allowed_service_tiers` | 3 | 1 | OpenAI Platform / LiteLLM Admin | Same-box console for the dial CLI already mints | Filed [#2111](https://github.com/naveenreddyalka/daari/issues/2111) |
| 303 | Route Codex PATs (`at-`) to the Codex backend on L6 | 3 | 2 | Portkey v2.32.0 OpenAI integration | Local tiers still win before Codex egress | Filed [#2112](https://github.com/naveenreddyalka/daari/issues/2112) |
| 304 | Prometheus counter for `X-Daari-Priority` admission overrides | 2 | 1 | LiteLLM / Portkey priority dashboards | Queue-steer pressure without a SaaS log plane | Filed [#2113](https://github.com/naveenreddyalka/daari/issues/2113) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 294, 296–298 | Rate-limit kind split; temperature omit; batches rotation; `/api/show` limits | 3–4 | 1–2 | LiteLLM / Ollama 0.40.14 | Byte-equivalence + signed push channels | Shipped (#2139–#2140, #2142–#2143) |
| 299 | Preserve assistant refusal parts in Responses input | 2 | 1 | Ollama 0.40.14 `/v1/responses` fix | Refusals survive tier hops | Shipped (#2150) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 291–293 | Message-threads; TPD web-ui; selection Grafana | 2–4 | 1–3 | Anthropic / LiteLLM / OpenRouter | TTFT parity + same-box console | Shipped (#2130–#2132) |
| 286–289 | OTel cost attrs; latency SLO; vLLM 0.33 notes; MCP oauth recipe | 2–3 | 1–2 | Portkey / OpenRouter / vLLM | Operator-owned traces + honest local tiers | Shipped (#2120–#2121, #2128–#2129) |
| 281–284 | LiteLLM LTS compare; offline PATCH; batch org webhook; request tags | 2–3 | 1–2 | LiteLLM / OpenRouter / Portkey | Honesty + air-gap + jobs + Signals on-box | Shipped (#2116–#2119) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): Portkey v2.33 Anthropic `auto_caching` (daari
`frontier.prompt_cache` already marks system blocks — revisit only if
top-level `cache_control` shape diverges); Portkey MCP access policies
(Prisma AIRS-only); Portkey OTel workspace name; Bedrock metadata map;
LiteLLM OpenAI Live `/v1/live/sessions` + Azure PTU split + M365 Copilot +
`gpt-live-1` outbound SIP (Realtime/WS family); LiteLLM 1.109.0 **stable**
cut (rc.1 baggage converted as row 322 — hold other rc highlights);
AutoTrust beyond Apple silicon; `gpt-6-cyber` (Daybreak); gpt-image-2.6
sunburst/flare catalog; Agents API `auto_review`; Anthropic text watermark
(metric-only); minute-grain spend buckets; fleet Redis EWMA; MCP SEP-3398;
OpenAI org external key management; Anthropic Compliance API; Models API
`between_tools` Sonnet-5.5-only; `gpt-6-rosalind`; Claude Code `groups` /
`guardrail_trace`; OpenRouter private-provider CRUD + S3/IAM; LiteLLM Admin
Chat UI / Lens; llama.cpp `/v1/realtime` + `POST /tts` + deferred tools;
Portkey claim-based JWT / WIF; OpenAI `/agents/automations`; Prisma AIRS
Agent Identity; Claude-on-GCP IAM (new dep — human); Anthropic hosted
skills; Claude Tag beta; Open Responses WS; Anthropic OTel export beta;
Prom exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer SSO;
Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign;
Ollama d1 Linux/Windows GA; local message-thread analogue (prefix store on
L3–L5 — only after explicit agent-loop ask); OpenAI CA/SG/KR/UAE/UK
residency labels beyond au/in/jp (expand only when operators ask).

Verified fine this run — don't re-audit: `regional_processing_factor` pins
only `us`/`eu` (`daari/pricing.py` `_REGIONAL_PROCESSING_PINS`);
`parse_request_tags` unions `X-Daari-Tags` + `metadata.tags` only (no
`baggage`); Grafana has Hard rejects by kind + Retired model rejects but no
service-tier allowlist panel; admin/web-ui inventory has no `allowed_ips`
column (field itself still open as row 316); LiteLLM compare still cites
1.108 RC framing (row 306); Portkey v2.33.1 fixes-only; Ollama top stable
**0.40.15**; LiteLLM LTS patch **1.108.1**; Portkey floor **v2.33.1**.

---

## Path to enterprise-grade — next 5 milestones

1. **Contain the leaked key** — IP allowlist (316) + console (323);
   revoke-subject (317); audit IP omit (314).
2. **Observe the TTFT / SLO / governance dials** — service-tier Grafana
   (321); thread counters (311); SLO demotion Prom (307) + PATCH (309) +
   console (313); selection Grafana shipped.
3. **Residency + mesh honesty** — AU/IN/JP pins (324); baggage→tags (322);
   OTel UA (312) + request-tag spans (308).
4. **Governance console tail** — service-tier admin/web-ui (302); then
   rows 62–67.
5. **Local runtime + fences + honesty** — AutoTrust (318); MiMo (319);
   fences (300, 305, 310, 315, 320, 325); Codex PAT L6 (303); offline Prom
   (279) + doctor (285); LiteLLM 1.108.1 floor (306); hot-reload (6).

---

## Changelog

- **2026-11-06 pm (observe + residency + baggage)** — Marked rows 301 and
  299 Shipped (afternoon merges). Outward: OpenAI AU/IN/JP residency
  endpoints convert; LiteLLM 1.109.0-rc.1 baggage→spend-tags converts;
  floors unchanged (Ollama 0.40.15, LiteLLM 1.108.1, Portkey v2.33.1).
  Filed rows 321–325: service-tier Grafana, baggage→tags, allowed_ips
  console, AU/IN/JP residency billing, afternoon fence.

- **2026-11-06 (leaked-key blast radius; Ollama 0.40.15 GA)** — Marked rows
  294, 296–298 Shipped. Outward: Ollama 0.40.15 GA; LiteLLM 1.108.1;
  Portkey v2.33.1; Anthropic IP-allowlist + sign-out-everywhere. Filed
  rows 316–320. Drained dead Actions PRD PR (stall issue needs human close).

- **2026-11-05 (TTFT/SLO observe tail; Portkey 2.33 UA; LiteLLM IP omit)** —
  Marked rows 281–284, 286–289, 291–293 Shipped. Adopted Nov-4 filings as
  306–310. Filed rows 311–315.

- **2026-11-03 pm → 10-28** — Condensed: governance console / Codex PAT /
  admission Prom through Apache 2.0 and this PRD's creation.
