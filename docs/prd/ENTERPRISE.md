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

## Where daari stands (verified in-tree, 2026-11-10 pm)

**Loop velocity.** Morning PRD (#2219) filed reasoning/BYOK/truncation
rows 355–359; overnight feature merges (allowed_ips, AU/IN/JP residency,
effort lever, VK grace) stay shipped. No new feature merges since 17:27
UTC. Open cliffs: 5.2 set (350–354), Kong deep-cut (345–349), morning
wave (355–359).

**Outward.** Flat vs morning. LiteLLM still **1.108.4 LTS** (11-09);
Ollama still **0.40.16**; Kong **2.3.1** = nginx CVE patches only;
Portkey **v2.33.1**, vLLM **0.33.0**, OpenRouter (10-29), MCP 2026-07-28,
OpenAI/Anthropic unchanged. No-delta is not a stop — convert watch +
inward debt.

**Inward theme: residency honesty + cache/failover dials + 5.2 advisor.**
`_REGIONAL_PROCESSING_PINS` stops at us/eu/au/in/jp while OpenAI hosts
already ship ca/sg/kr/gb/ae (unit pin asserts `sg` → 1.0× today).
`prompt_cache` only marks the last system block — no top-level Anthropic
`cache_control` auto dial (Portkey 2.33). `RETRYABLE_STATUS` misses
501/522 that Kong's `http_5xx` failover catches. No advisor-tool gate for
Fable/Mythos 5.2 same-model pairing (Anthropic 400 before egress).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 360 | Expand OpenAI residency 1.10× + docs to CA/SG/KR/GB/AE | 3 | 1 | OpenAI regional hosts + invoice uplift | Same-box ledger matches regional invoice; storage-vs-processing honesty next to the pin | Filed [#2220](https://github.com/naveenreddyalka/daari/issues/2220) |
| 361 | Opt-in Anthropic `auto_caching` via top-level `cache_control` | 3 | 2 | Portkey 2.33.0 auto_caching | Agent loops get Claude automatic cache without a SaaS config plane | Filed [#2221](https://github.com/naveenreddyalka/daari/issues/2221) |
| 362 | Opt-in failover on any HTTP 5xx incl. 501/522 | 3 | 2 | Kong 2.3.0 `http_5xx` failover_criteria | Local/frontier 5xx fail over on-box; no Cedar dep | Filed [#2222](https://github.com/naveenreddyalka/daari/issues/2222) |
| 363 | Require Fable/Mythos 5.2-compatible advisor model | 3 | 2 | Anthropic 11-09 advisor pairing gate | Fail-fast before the cloud 400; agent loop stays on-box | Filed [#2223](https://github.com/naveenreddyalka/daari/issues/2223) |
| 364 | Integration fence for the 11-10 evening wave | 2 | 2 | — (testability) | Hermetic proof: residency pins, auto_caching, 5xx failover, advisor gate | Filed [#2224](https://github.com/naveenreddyalka/daari/issues/2224) |
| 355 | Round-trip OpenAI encrypted reasoning on `/v1/messages` across turns | 4 | 2 | LiteLLM 1.108.4 LTS reasoning fix | One box fronts both vendors; reasoning fidelity survives any executor, no SaaS middle layer | Filed [#2214](https://github.com/naveenreddyalka/daari/issues/2214) |
| 356 | Honor `truncation` auto/disabled on `/v1/responses` | 3 | 2 | Ollama 0.40.16 honors it; OpenAI semantics | Local tiers hit context walls first; compact on-box, payload never leaves | Filed [#2215](https://github.com/naveenreddyalka/daari/issues/2215) |
| 357 | Per-team frontier credential binding (team BYOK) | 4 | 3 | LiteLLM team BYOK (1.108.4 precedence fix) | Each team's L6 bills to their own invoice; shared local tiers stay $0 | Filed [#2216](https://github.com/naveenreddyalka/daari/issues/2216) |
| 358 | Ripple Preview L4/L5 agentic-coding recipe (Ollama ≥ 0.40.16) | 3 | 1 | Ollama 0.40.16 `ripple-preview` | $0 on-box coding agent tier with honest 65B-dense VRAM guidance | Filed [#2217](https://github.com/naveenreddyalka/daari/issues/2217) |
| 359 | Integration fence for the 11-09/11-10 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny/PATCH, residency 1.10×, effort lever, VK grace | Filed [#2218](https://github.com/naveenreddyalka/daari/issues/2218) |
| 350 | Ship Claude Fable 5.2 / Mythos 5.2 catalog rates + caps + fast mode | 4 | 2 | Anthropic Platform 11-09 list prices | Honest on-box ledger vs invoice; local tiers stay $0 | Filed [#2204](https://github.com/naveenreddyalka/daari/issues/2204) |
| 351 | Drop Fable/Mythos 5.2 thinking when failover switches to another model | 4 | 2 | Anthropic mid-conversation drop (11-09) | On-box switch owns the strip; agent loop survives without a cloud round-trip | Filed [#2205](https://github.com/naveenreddyalka/daari/issues/2205) |
| 352 | Require `computer_toolset_20260801` on Fable/Mythos 5.2 (reject `computer_20251124`) | 3 | 2 | Anthropic 11-09 toolset gate | Gateway rewrite/fail-fast before the 400; Bedrock exception kept | Filed [#2206](https://github.com/naveenreddyalka/daari/issues/2206) |
| 353 | Config ownership + PATCH for `routing.baggage_to_tags` | 3 | 1 | LiteLLM baggage→tags / Portkey Complete Logs | Hot-edit mesh-identity dial on the same-box console | Filed [#2207](https://github.com/naveenreddyalka/daari/issues/2207) |
| 354 | Integration fence for the 11-09 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: baggage tags, service-tier Grafana, 5.2 catalog smoke | Filed [#2208](https://github.com/naveenreddyalka/daari/issues/2208) |
| 345 | Default `drop_block` thinking binding on preserved-thinking Claude (replay-after-prefix-change 400s) | 4 | 2 | Kong 2.3.0 default drop_block | daari mutates the prefix (compress/compact) so daari owns the binding fix | Filed [#2196](https://github.com/naveenreddyalka/daari/issues/2196) |
| 346 | Bill server-side tools beyond web search + per-tool `tool_usage` breakdown | 4 | 2 | Kong 2.3.0 `usage.tool_cost`/`tool_usage` | On-box ledger reconciles with the provider invoice, no SaaS analytics | Filed [#2197](https://github.com/naveenreddyalka/daari/issues/2197) |
| 347 | Opt-in in-flight budget reservation (pre-charge estimate, settle actual) | 4 | 3 | Kong 2.3.0 rate-limit cost pre-charge | Ledger + admission + pricing on one box; parallel bursts can't blow the window | Filed [#2198](https://github.com/naveenreddyalka/daari/issues/2198) |
| 348 | Opt-in cardinality-capped per-key label on Prometheus series | 3 | 2 | Kong 2.3.0 `enable_credential_attribute` + limit | Per-key FinOps from the same-box scrape; `team_metrics` pattern proven | Filed [#2199](https://github.com/naveenreddyalka/daari/issues/2199) |
| 349 | Integration fence for the 11-08/11-09 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny, revoke-subject, AutoTrust, MiMo | Filed [#2200](https://github.com/naveenreddyalka/daari/issues/2200) |
| 340 | Prebuilt OpenAI/Anthropic/Gemini credential guardrail patterns | 3 | 1 | LiteLLM 1.110.0-dev.2 credential patterns | On-box scrub of provider keys before any hop | Filed [#2186](https://github.com/naveenreddyalka/daari/issues/2186) |
| 341 | Config ownership + PATCH for `guardrails.log_blocked_content` | 3 | 1 | Kong / LiteLLM control-plane toggles | Hot-edit forensics dial on the operator console | Filed [#2187](https://github.com/naveenreddyalka/daari/issues/2187) |
| 342 | `reasoning_effort`/`output_config.effort` `none` disables Claude 5.5 adaptive thinking | 3 | 2 | LiteLLM 1.110.0-dev.2 Anthropic fix | Zero-thinking means zero thinking tokens on L6 | Filed [#2188](https://github.com/naveenreddyalka/daari/issues/2188) |
| 343 | Prometheus + stats counters for input/output cost USD | 3 | 2 | Kong 2.3.0 analytics / LiteLLM Admin | Same-box scrape once the cost split lands | Filed [#2189](https://github.com/naveenreddyalka/daari/issues/2189) |
| 344 | Integration fence for the 11-08 morning MCP/Kong wave | 2 | 2 | — (testability) | Hermetic proof: MCP fidelity, cost split, blocked content | Filed [#2190](https://github.com/naveenreddyalka/daari/issues/2190) |
| 335 | Faithful MCP egress tool results (extract `content[]`, lift `str()[:4000]`) | 4 | 2 | LiteLLM 1.108.3 LTS >1 MiB fix | Byte-faithful local tool results are the product | Filed [#2180](https://github.com/naveenreddyalka/daari/issues/2180) |
| 336 | MCP egress streamable-HTTP conformance (Accept + SSE-framed replies) | 3 | 2 | LiteLLM 1.108.3 SSE framing fix | Spec-default local MCP servers just work | Filed [#2181](https://github.com/naveenreddyalka/daari/issues/2181) |
| 337 | Split request cost into input/output components everywhere cost shows | 3 | 2 | Kong AI Gateway 2.3.0 analytics | FinOps truth in headers + operator-owned OTel, no SaaS | Filed [#2182](https://github.com/naveenreddyalka/daari/issues/2182) |
| 338 | Opt-in `guardrails.log_blocked_content` for block forensics | 3 | 2 | Kong 2.3.0 `log_blocked_content` | Blocked payloads stay in the on-box event store | Filed [#2183](https://github.com/naveenreddyalka/daari/issues/2183) |
| 339 | Integration fence for the 11-07/11-08 overnight wave | 2 | 2 | — (testability) | Hermetic proof: SLO PATCH/UI, threads, UA spans, IP omit | Filed [#2184](https://github.com/naveenreddyalka/daari/issues/2184) |
| 330 | Grafana panels for `daari_virtual_model_slo_demotion_total` | 2 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box scrape for the SLO dial just shipped | Filed [#2169](https://github.com/naveenreddyalka/daari/issues/2169) |
| 331 | Promote compare-litellm floor to the live LTS (1.108.4 as of 11-09) | 2 | 1 | LiteLLM release notes | Honest LTS patch floor without a runtime dep | Filed [#2170](https://github.com/naveenreddyalka/daari/issues/2170) |
| 332 | compare-openrouter: Auto + Auto Code local-first positioning | 3 | 1 | OpenRouter Auto / Auto Code (11-06) | On-box virtual-models + signal_overrides vs hosted pick | Filed [#2171](https://github.com/naveenreddyalka/daari/issues/2171) |
| 333 | Config ownership + PATCH for `observability.otel_include_request_tags` | 3 | 1 | Portkey Complete Logs / LiteLLM tag dashboards | Hot-edit tag export on operator-owned OTel | Filed [#2172](https://github.com/naveenreddyalka/daari/issues/2172) |
| 334 | Integration fence for the 11-07 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: SLO demotion Prom + OTel request tags | Filed [#2173](https://github.com/naveenreddyalka/daari/issues/2173) |
| 326–327 | `reasoning_effort` signal lever; last-known-good VK grace across PG blips | 4 | 2 | OpenRouter Auto / LiteLLM 1.108.2 | Effort on-box; local tiers serve through control-plane restarts | Shipped (#2212, #2213) |
| 328 | Cost-aware virtual-model selection mode | 3 | 2 | OpenRouter Auto Router live-pricing factor | Zero-cost local tiers sort first from the arithmetic | Filed [#2164](https://github.com/naveenreddyalka/daari/issues/2164) |
| 329 | Integration fence for the 11-06/11-07 overnight wave | 2 | 2 | — (testability) | Hermetic proof: Codex PAT, priority Prom, tier inventory | Filed [#2165](https://github.com/naveenreddyalka/daari/issues/2165) |
| 321–324 | Service-tier Grafana; baggage→tags; allowed_ips console; AU/IN/JP residency 1.10× | 2–3 | 1–2 | OpenAI / LiteLLM / Anthropic Console | Governance + residency dials on the same-box console | Shipped (#2202, #2203, #2210, #2211) |
| 325 | Integration fence for the 11-06 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: refusals + service-tier metrics | Filed [#2156](https://github.com/naveenreddyalka/daari/issues/2156) |
| 316–319 | IP allowlist CIDR; revoke-subject kill switch; AutoTrust family; MiMo recipe | 3–4 | 1–2 | Anthropic Console / Ollama 0.40.15 | Blast-radius + local catalog on the same-box console | Shipped (#2192–#2195) |
| 320 | Integration fence for the 11-05/11-06 overnight wave | 2 | 2 | — (testability) | Hermetic proof: temp omit, rate kinds, show limits, rotation | Filed [#2148](https://github.com/naveenreddyalka/daari/issues/2148) |
| 309, 311–314 | SLO PATCH + console; message-thread Prom; UA spans; audit IP omit | 3 | 1–2 | LiteLLM / Portkey / Anthropic / OpenRouter | Governance + privacy dials on the same-box console | Shipped (#2175–#2179) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 307, 308 | SLO demotion Prom/stats; opt-in request tags on OTel GenAI spans | 3 | 1 | OpenRouter / Portkey Complete Logs | Operator-owned traces next to local-tier cost attrs | Shipped (#2166, #2168) |
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
lever (file after rows 326/328 land); Fable/Mythos 5.2 30-day retention /
ZDR carve-out honesty (file after 350 lands; advisor pairing converted
to row 363); Kong 2.3.0 Cedar `access-policy-engine` + CEL
`allow_when`/`deny_when` tool ACL + Token Vault credential placement
(expression engine = new dep or heavy — human sign-off; `http_5xx`
converted to row 362); Grafana panels for input/output cost USD (after
343); LiteLLM `1.110.0-dev` remainder beyond 340/342 (provider-reported
`usage.cost`, tenant session affinity, Lens-split Helm, per-key/team
prompt-storage off, deployment weights, Responses SSE framing preserve;
empty-reply cache poison already covered — hold for a stable cut);
Kong 2.3.1 (11-10) = nginx CVE patches only, floor stays 2.3.0 semantics;
Ollama top stable floor 0.40.16 (0.40.15 recipes unaffected); Portkey MCP
access policies (Prisma AIRS-only); Portkey OTel workspace name; Bedrock
metadata map; LiteLLM OpenAI Live `/v1/live/sessions` + Azure PTU + M365
Copilot + `gpt-live-1` SIP (Realtime/WS); AutoTrust beyond Apple silicon;
`gpt-6-cyber` (Daybreak); gpt-image-2.6 sunburst/flare; Agents API
`auto_review`; Anthropic text watermark (metric-only); minute-grain spend;
fleet Redis EWMA; MCP SEP-3398 (~March 2027); OpenAI org external key
management; Anthropic Compliance API; `between_tools` Sonnet-5.5-only;
`gpt-6-rosalind`; Claude Code `groups` / `guardrail_trace`; OpenRouter
private-provider CRUD; LiteLLM Admin Chat UI / Lens; llama.cpp
`/v1/realtime` + `POST /tts`; Portkey claim JWT / WIF; OpenAI
`/agents/automations`; Prisma AIRS Agent Identity; Claude-on-GCP IAM
(new dep — human); Anthropic hosted skills; Claude Tag beta; Open
Responses WS; Anthropic OTel export beta; Prom exemplars +
`gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer SSO; Kong
Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign;
Ollama d1 Linux/Windows GA; local message-thread analogue (only after
explicit agent-loop ask); A2A 1.1 RC (wait for two-SDK gate).

Verified fine this run — don't re-audit: morning's LiteLLM 1.108.4
`background` / cross-model thinking / facade list / missing `/bedrock` +
`/v1/videos` checks still hold; Kong 2.3.1 still CVE-only; cache-write
TTL pricing + `redact_secrets` unchanged; Portkey auto_caching divergence
confirmed (block-level only → row 361); residency pin set still excludes
ca/sg/kr/gb/ae (→ row 360).

---

## Path to enterprise-grade — next 5 milestones

1. **Agent-loop fidelity on every executor** — 5.2 catalog rates + fast
   mode (350); thinking strip on model switch (351); advisor pairing
   (363); OpenAI encrypted-reasoning on Messages (355);
   `computer_toolset_20260801` (352); drop_block (345); `truncation`
   (356); MCP egress (335–336); CEL watch.
2. **FinOps + tenancy that reconcile** — CA/SG/KR/GB/AE residency uplift
   (360); per-team frontier BYOK (357); server-side tool billing (346);
   in-flight budget reservation (347); cost input/output split (337) +
   Prom/stats (343); per-key metric label (348).
3. **Contain the leaked key** — provider credential patterns (340);
   blocked-content forensics (338) + ownership (341).
4. **Route like the new Auto Router** — Claude `effort=none` (342);
   auto_caching dial (361); any-5xx failover (362); cost-aware selection
   (328); Ripple coding tier (358); baggage PATCH (353); coding-router
   recipe (watch); Grafana for SLO demotions (330).
5. **Survive the control-plane blip + honest compare** — offline Prom
   (279) + doctor (285); hot-reload (6); OTel tags PATCH (333); failover
   panels (274); LiteLLM LTS + OpenRouter Auto compare (331–332); fences
   (300, 305, 310, 315, 320, 325, 329, 334, 339, 344, 349, 354, 359,
   364); then rows 62–67.

---

## Changelog

- **2026-11-10 pm (residency, auto_caching, 5xx failover, advisor gate)** —
  Outward flat vs morning (LiteLLM 1.108.4, Ollama 0.40.16, Kong 2.3.1
  CVE-only). Converted watch + inward: OpenAI CA/SG/KR/GB/AE residency
  1.10× + docs (row 360 — pins stop at au/in/jp today), Portkey-parity
  Anthropic top-level `auto_caching` (361), Kong `http_5xx` without Cedar
  (362), Fable/Mythos 5.2 advisor same-model fail-fast (363), evening
  fence (364). Watch drops converted auto_caching / residency /
  http_5xx / advisor; retains Cedar/CEL/Token Vault + 5.2 ZDR after 350.

- **2026-11-10 (reasoning fidelity, tenant BYOK, truncation honesty)** —
  Marked rows 323–324, 326–327 Shipped (allowed_ips console, residency
  pins, effort lever, VK grace — all overnight). Outward: LiteLLM
  v1.108.4 LTS + Ollama v0.40.16 (both 11-09); Kong 2.3.1 = CVE-only;
  rest flat. Converted inward: OpenAI encrypted-reasoning round-trip on
  Messages (row 355 — `openai_executor` has zero reasoning handling),
  `truncation` auto/disabled honesty (356 — parsed then dropped today),
  per-team frontier credential binding (357 — keys are global-only),
  Ripple Preview coding recipe (358), overnight fence (359). Verified
  not present: the 1.108.4 `background` billing leak and cross-model
  thinking replay; facade list shapes already fine.

- **2026-11-09 pm (Claude Fable/Mythos 5.2 cliff)** — Marked rows
  321–322 Shipped (service-tier Grafana; baggage→tags). Outward: Anthropic
  launched Fable 5.2 / Mythos 5.2; other trains flat vs morning. Filed
  catalog rates + fast mode (350), thinking strip on model switch (351),
  `computer_toolset_20260801` gate (352), baggage_to_tags ownership
  PATCH (353), afternoon fence (354). Watch gains advisor pairing /
  ZDR honesty (after 350), 1.108.3 compare bump, A2A 1.1 RC. Verified:
  5xx already hard-fails the circuit breaker; TTL cache-write + request
  redaction still covered.

- **2026-11-09 (Kong 2.3.0 deep cut: thinking binding, tool billing,
  pre-charge)** — Marked rows 316–319 Shipped (#2192–#2195 overnight).
  Outward flat on every train; converted the unmined Kong AI Gateway
  2.3.0 remainder inward: default `drop_block` thinking binding (row
  345 — daari replays thinking *and* mutates the prefix), per-call
  server-side tool billing + `tool_usage` breakdown (346), in-flight
  budget pre-charge (347), cardinality-capped per-key Prom label (348),
  plus the overnight fence (349). Verified covered: TTL-keyed cache-write
  pricing, request_log redaction, config price overrides.

- **2026-11-08 pm (1.110-dev privacy/effort converts; FinOps scrape)** —
  Outward flat vs morning; converted LiteLLM 1.110.0-dev.2 credential
  patterns + Claude `effort=none` (rows 340, 342); filed ownership for
  `log_blocked_content` (341), input/output cost Prom/stats (343), and
  the morning-wave fence (344). Watch retains prompt-storage off,
  deployment weights, Responses SSE framing, Kong Cedar/CEL/`http_5xx`.

- **2026-11-08 (tool-result fidelity; Kong 2.3.0 parity)** — Marked rows
  309, 311–314 Shipped (#2175–#2179, the whole 11-05 wave overnight).
  Outward: Kong AI Gateway runtime 2.3.0 (cost split, log_blocked_content,
  Cedar/CEL → Watch); LiteLLM 1.108.3 LTS MCP >1 MiB SSE fix;
  1.110.0-dev.2 → Watch. Inward: MCP egress repr-truncates results at
  4000 chars and cannot parse SSE framing. Filed rows 335–339.

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

- **2026-11-06 → 10-28** — Condensed: leaked-key blast radius + Ollama
  0.40.15 GA (rows 316–325; dead Actions PR #2127 drained, stall issue
  #2141 needs human close); TTFT/SLO observe tail (311–315); governance
  console / Codex PAT / admission Prom; Ollama 0.40.14 parity;
  message-threads / TPD / selection Grafana; trace cost / latency SLO /
  vLLM / MCP cc; LTS / air-gap / batch default / request tags; through
  Apache 2.0 and this PRD's creation.
