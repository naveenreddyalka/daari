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

## Where daari stands (verified in-tree, 2026-11-13 pm)

**Loop velocity.** Morning PRD #2270 merged (rows 385–389). Overnight
wave still Filed (MCP cancel, abandoned-stream bill, session pins,
llama.cpp pin, fence). Cost-split counters shipped (#2263) but Grafana
panels missing (→ 392).

**Outward.** **LiteLLM 1.108.8 LTS** (11-13 evening): Azure Decisions
(#48529 → compare 393), file-id spelling ownership (#51503 → watch /
compare), `mcp_all` wildcard (#51578 → compare). **1.111.0-dev.2**
(11-13 evening) customer-org budgets / saturation fallback — hold for
stable; mined refused-leg billing #50735 → 391. **OpenRouter
Extractions API** alpha (11-10) — Decisions envelope + `fields` map →
390. Flat vs morning: Kong 2.3.1, Portkey 2.33.1, Ollama 0.40.17-rc0,
vLLM 0.33.0rc3 / 0.34.0rc2, llama.cpp 1.0.0 (+ b12366 tags).

**Inward theme: typed extraction + every billed attempt.** No
`/v1/extractions` next to Decisions (→ 390). Failover that walks past a
billed refusal/safeguard leg undercounts the ledger (→ 391). Input/
output USD counters exist without dashboard panels (→ 392). Compare
LTS floor still behind 1.108.8 (→ 393).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 390 | `POST /v1/extractions` — OpenRouter Extractions twin on Decisions/System One | 4 | 3 | OpenRouter Extractions alpha (11-10) | Local System One absorbs doc-intel at $0; one box owns Decisions + Extractions | Filed [#2271](https://github.com/naveenreddyalka/daari/issues/2271) |
| 391 | Bill refused/safeguard legs the router falls back from | 4 | 2 | LiteLLM 1.111-dev #50735 | Same-box ledger matches every billed attempt, not only the answer the client sees | Filed [#2272](https://github.com/naveenreddyalka/daari/issues/2272) |
| 392 | Grafana panels for `daari_cost_input_usd_total` / `daari_cost_output_usd_total` | 2 | 1 | Kong AI Gateway FinOps dashboards | Input vs output USD on the same-box scrape; local paths stay 0/0 | Filed [#2273](https://github.com/naveenreddyalka/daari/issues/2273) |
| 393 | compare-litellm: LTS floor → 1.108.8; Azure Decisions + MCP `mcp_all` notes | 2 | 1 | LiteLLM 1.108.8 release notes | Honest floor + local-first Decisions positioning next to tonight's LTS | Filed [#2274](https://github.com/naveenreddyalka/daari/issues/2274) |
| 394 | Integration fence for the 11-13 evening wave | 2 | 2 | — (testability) | Hermetic proof: extractions schema, refused-leg sum, cost panels, LTS pin | Filed [#2275](https://github.com/naveenreddyalka/daari/issues/2275) |
| 385 | MCP `notifications/cancelled` — emit on egress abort, honor on ingress | 4 | 2 | llama.cpp v1.0.0 server (#32025) | Abandoned agent work stops burning local GPU + egress quota the moment the caller hangs up | Filed [#2265](https://github.com/naveenreddyalka/daari/issues/2265) |
| 386 | Settle ledger spend for frontier streams the client abandons | 4 | 2 | LiteLLM (python path; 1.111-dev #50425 native parity) | Same-box ledger matches the invoice even for aborted streams; closes a budget bypass | Filed [#2266](https://github.com/naveenreddyalka/daari/issues/2266) |
| 387 | Session pins must not replay across conversations under a shared key | 4 | 2 | LiteLLM 1.111-dev #50741; Kong 2.3.0 x-opencode header | Prefix-hash gate on-box — no vendor header convention needed | Filed [#2267](https://github.com/naveenreddyalka/daari/issues/2267) |
| 388 | llama.cpp v1.0.0: guide pin, security opt-ins, TTS target, FP8/MoE capacity levers | 3 | 1 | llama.cpp release docs | daari is the governance layer the engine lacks; pin its first stable major honestly | Filed [#2268](https://github.com/naveenreddyalka/daari/issues/2268) |
| 389 | Integration fence for the 11-12/11-13 overnight wave | 2 | 2 | — (testability) | Hermetic proof: forensics PATCH, effort none, cost counters, drop_block | Filed [#2269](https://github.com/naveenreddyalka/daari/issues/2269) |
| 380 | `previous_response_id` must not replay failed/cancelled turns | 4 | 2 | LiteLLM 1.108.7 LTS (#48647) | On-box store skips poison history; local+frontier share one chain contract | Filed [#2255](https://github.com/naveenreddyalka/daari/issues/2255) |
| 381 | Honor or honestly declare `max_tool_calls` (Responses-only fields) | 3 | 2 | LiteLLM 1.108.7 (#48655 drop_params / 400) | Enforce or `dropped_params` on-box — never silent, never smuggle to Bedrock | Filed [#2256](https://github.com/naveenreddyalka/daari/issues/2256) |
| 382 | Claude Managed Agents self-hosted → daari Anthropic facade recipe | 4 | 2 | Anthropic CMA (hosted default); any Claude-shaped gateway | Local L0–L5 absorb CMA repeats at $0 before frontier | Filed [#2257](https://github.com/naveenreddyalka/daari/issues/2257) |
| 383 | compare-litellm: LTS floor → 1.108.7; Responses bridge + failed-turn positioning | 3 | 1 | LiteLLM release notes | Honest floor + diskcache differentiator next to tonight's LTS | Filed [#2258](https://github.com/naveenreddyalka/daari/issues/2258) |
| 384 | Integration fence for the 11-12 evening 1.108.7 / CMA wave | 2 | 2 | — (testability) | Hermetic proof: failed-chain, max_tool_calls honesty, cma-server metadata | Filed [#2259](https://github.com/naveenreddyalka/daari/issues/2259) |
| 375 | Bill frontier image generations/edits from upstream `usage`; gpt-image-2.6 catalog rates | 4 | 2 | OpenAI token-billed images; LiteLLM 1.108.6 Gemini image-edit billing | Image spend lands in the same-box ledger/budgets that meter chat | Filed [#2249](https://github.com/naveenreddyalka/daari/issues/2249) |
| 376 | Bill the frontier ASR leg honestly (duration/token rates); local stays $0 | 3 | 2 | OpenAI per-minute/token ASR billing | The fallback that costs money is the leg the ledger must meter | Filed [#2250](https://github.com/naveenreddyalka/daari/issues/2250) |
| 377 | Honor `tool_choice: allowed_tools` (nested + flat) across Anthropic + local backends | 3 | 2 | LiteLLM 1.108.6 LTS (#49043/#50467) | One tool-governance contract at the edge for every executor | Filed [#2251](https://github.com/naveenreddyalka/daari/issues/2251) |
| 378 | Prove + fence client credential-field hygiene (immune to the litellm#51254 class); floors 1.109.1/1.108.6 | 3 | 1 | LiteLLM (after its emergency patch) | Allowlist payloads never needed the patch — argue it with a test | Filed [#2252](https://github.com/naveenreddyalka/daari/issues/2252) |
| 379 | Integration fence for the 11-11/11-12 overnight wave | 2 | 2 | — (testability) | Hermetic proof: MCP egress fidelity, cost split, forensics, patterns | Filed [#2253](https://github.com/naveenreddyalka/daari/issues/2253) |
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Filed [#2238](https://github.com/naveenreddyalka/daari/issues/2238) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Filed [#2239](https://github.com/naveenreddyalka/daari/issues/2239) |
| 372 | Per-model daily `rpd`/`tpd` + virtual-model failover on exhaust | 3 | 2 | LiteLLM 1.109.0 deployment daily limits | Burn one L6 daily quota; walk continues on local peers | Filed [#2240](https://github.com/naveenreddyalka/daari/issues/2240) |
| 373 | Streams that `abort` or omit `finish_reason` fail visibly + failover | 4 | 2 | LiteLLM 1.109.0 stream-failure visibility | On-box failover salvages cancelled/truncated turns | Filed [#2241](https://github.com/naveenreddyalka/daari/issues/2241) |
| 374 | Integration fence for the 11-11 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: coding compose, Carbon rates, daily skip, abort | Filed [#2242](https://github.com/naveenreddyalka/daari/issues/2242) |
| 365 | Honest `stop_reason` on `/v1/messages` (capture `pause_turn`/`max_tokens`/`refusal`) | 4 | 2 | LiteLLM 1.109.0 pause_turn + length fixes | One box fronts local + frontier; truncation and pauses surface truthfully on one contract | Filed [#2232](https://github.com/naveenreddyalka/daari/issues/2232) |
| 366 | Guardrails scan assistant `tool_calls` arguments (+ opt-in system scan) | 4 | 2 | LiteLLM 1.109.0 hide-secrets surface fix | Secrets scrubbed on-box before any byte leaves; #2186 patterns need the surface | Filed [#2233](https://github.com/naveenreddyalka/daari/issues/2233) |
| 367 | Streamed L0 hits must not drop cached `tool_calls` | 3 | 2 | LiteLLM 1.109.0 streamed-cache-hit fix | The $0 cache tier must be byte-faithful or agent loops can't trust it | Filed [#2234](https://github.com/naveenreddyalka/daari/issues/2234) |
| 368 | compare-litellm: 1.109.0 stable floor + 1.108.5 LTS + disk-cache removal positioning | 3 | 1 | LiteLLM release notes | They removed disk caching; daari's L1 **is** a local diskcache — hard differentiator | Filed [#2235](https://github.com/naveenreddyalka/daari/issues/2235) |
| 369 | Integration fence for the 11-10/11-11 overnight wave | 2 | 2 | — (testability) | Hermetic proof: cost-aware selection prefers $0 local; SLO panel pinned | Filed [#2236](https://github.com/naveenreddyalka/daari/issues/2236) |
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
| 346 | Bill server-side tools beyond web search + per-tool `tool_usage` breakdown | 4 | 2 | Kong 2.3.0 `usage.tool_cost`/`tool_usage` | On-box ledger reconciles with the provider invoice, no SaaS analytics | Filed [#2197](https://github.com/naveenreddyalka/daari/issues/2197) |
| 347 | Opt-in in-flight budget reservation (pre-charge estimate, settle actual) | 4 | 3 | Kong 2.3.0 rate-limit cost pre-charge | Ledger + admission + pricing on one box; parallel bursts can't blow the window | Filed [#2198](https://github.com/naveenreddyalka/daari/issues/2198) |
| 348 | Opt-in cardinality-capped per-key label on Prometheus series | 3 | 2 | Kong 2.3.0 `enable_credential_attribute` + limit | Per-key FinOps from the same-box scrape; `team_metrics` pattern proven | Filed [#2199](https://github.com/naveenreddyalka/daari/issues/2199) |
| 349 | Integration fence for the 11-08/11-09 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny, revoke-subject, AutoTrust, MiMo | Filed [#2200](https://github.com/naveenreddyalka/daari/issues/2200) |
| 333, 335–338, 340 | OTel-tags ownership; MCP egress fidelity + SSE framing; cost input/output split; block forensics; credential patterns | 3–4 | 1–2 | Kong 2.3.0 / LiteLLM 1.108.3–1.110-dev | Byte-faithful egress + on-box forensics and FinOps | Shipped (#2230, #2244–#2248) |
| 341–343, 345 | `log_blocked_content` ownership; effort `none` disables thinking; input/output cost counters; default `drop_block` binding | 3–4 | 1–2 | Kong 2.3.0 / LiteLLM 1.110-dev | Forensics, thinking, and FinOps dials on the same-box console and scrape | Shipped (#2261–#2264) |
| 344 | Integration fence for the 11-08 morning MCP/Kong wave | 2 | 2 | — (testability) | Hermetic proof: MCP fidelity, cost split, blocked content | Filed [#2190](https://github.com/naveenreddyalka/daari/issues/2190) |
| 339 | Integration fence for the 11-07/11-08 overnight wave | 2 | 2 | — (testability) | Hermetic proof: SLO PATCH/UI, threads, UA spans, IP omit | Filed [#2184](https://github.com/naveenreddyalka/daari/issues/2184) |
| 330–332 | SLO-demotion Grafana; compare LTS floor; OpenRouter Auto compare | 2–3 | 1 | OpenRouter / LiteLLM release notes | Same-box scrape + honest compare floors | Shipped (#2227–#2229) |
| 334 | Integration fence for the 11-07 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: SLO demotion Prom + OTel request tags | Filed [#2173](https://github.com/naveenreddyalka/daari/issues/2173) |
| 326–328 | `reasoning_effort` signal lever; VK grace across PG blips; cost-aware selection | 3–4 | 2 | OpenRouter Auto / LiteLLM 1.108.2 | Effort + $0-first arithmetic on-box; serve through control-plane restarts | Shipped (#2212, #2213, #2226) |
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

Watch rows (do not file yet): **MCP file-uploads** draft
(`io.modelcontextprotocol/files`, blog 11-10 — no reference impl; ~EOY);
**LiteLLM 1.111.0-dev.2** (11-13 evening — hold for stable: customer
org/team/member budgets + portal UI, `fallback_on_saturation`, annual
budget reset, access-group vector stores, Deep Research cost binding;
prior-dev remainder: per-model tpm/rpm maps, OpenSearch pass-through,
encrypted-content boundary #50750); **1.110.0-rc.2** (hold —
Agent Skills Hub, Rust-only router, Responses named-SSE / no Chat
`[DONE]`, response-id ownership 403); 1.108.7 remainder (Gemini
batches + Azure gpt-image edits — buyer ask); 1.109.0 remainder (K8s
headless-pod discovery; shadow rates; request-log retention); Opus
4.8 fast-mode removal 11-30; Ollama 0.40.17-rc0 (MLX concurrent gen —
hold for GA); vLLM 0.33/0.34 rc; **OpenRouter guardrail-policies
API**; Fable/Mythos 5.2 ZDR honesty (after 350); Kong Cedar/CEL/Token
Vault (new dep — human); Portkey MCP policies (Prisma AIRS-only);
OpenAI Live/SIP / Realtime/WS; AutoTrust beyond Apple silicon;
`gpt-6-cyber`; Agents `auto_review`; Anthropic watermark / Compliance
API / hosted skills; CMA-as-provider (buyer ask); minute-grain spend;
fleet Redis EWMA; MCP SEP-3398; OpenAI org external keys;
`between_tools`; `gpt-6-rosalind`; Claude Code `groups` /
`guardrail_trace`; OpenRouter private-provider CRUD; LiteLLM Admin
Chat / Lens / ID-JAG; llama.cpp `/v1/realtime`; Portkey JWT/WIF;
Prisma AIRS Agent Identity; Claude-on-GCP IAM (new dep); Open
Responses WS; Prom exemplars + `gen_ai.agent.*`; SCIM + multi-issuer
SSO; Kong Skills/A2A; certifi emSign; Ollama d1 GA; local
message-thread analogue (after ask); A2A 1.1 RC (two-SDK gate).

Verified fine this run (vs LiteLLM 1.108.8 / 1.111-dev.2 / OpenRouter
Extractions) — don't re-audit: Decisions + System One path exists
(390 is Extractions twin, not Decisions); Responses already emit named
SSE ending at `response.completed` without Chat `[DONE]` (1.110
Responses framing class covered); response `owner_key_id` deny for
foreign virtual keys exists (#453 class); `upstream.request_deadline_seconds`
covers LiteLLM `total_timeout`; file store ownership is exact
`file-{uuid}` (provider spelling normalize stays compare/watch until
a pass-through files surface needs it); semantic-router / GPTCache /
RouteLLM / OptiLLM flat. Still parity: credential hygiene (378),
mid-stream fallback continuation, session repin after failover,
`prompt_cache_retention`, `redacted_thinking`.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing truth everywhere money moves** — refused-leg sum (391);
   abandoned-stream settlement (386); image generations/edits (375);
   frontier ASR (376); Gemini 4 Carbon/Argon (371); 5.2 catalog (350);
   server-side tool billing (346); in-flight reservation (347); per-key
   label (348); daily `rpd`/`tpd` (372); residency uplift (360);
   per-team BYOK (357); Grafana input/output panels (392).
2. **Abandoned work stops and stays attributed** — MCP cancellation
   notifications (385); session-pin isolation (387); abort/
   `finish_reason` honesty (373); honest `stop_reason` (365).
3. **Agent-loop / Responses / Extractions fidelity** — Extractions facade
   (390); skip failed `previous_response_id` turns (380);
   `max_tool_calls` honesty (381); streamed cache tool_calls (367);
   `allowed_tools` (377); thinking strip (351); advisor (363);
   encrypted-reasoning (355); toolset gate (352); `truncation` (356).
4. **CMA, containment, and routing like Auto Router** — Managed
   Agents → daari recipe (382); credential hygiene fence (378); scan
   tool_call args (366); coding-router (370); auto_caching (361);
   any-5xx (362); Ripple (358); baggage PATCH (353).
5. **Local engine floor + survive the blip + honest compare** —
   llama.cpp v1.0.0 pin (388); LTS floor 1.108.8 compare (393; prior
   368/383); offline Prom (279) + doctor (285); hot-reload (6);
   failover panels (274); fences through 394; then 62–67.

---

## Changelog

- **2026-11-13 pm (Extractions + LTS 1.108.8 + refused-leg truth)** —
  Outward: OpenRouter Extractions alpha → 390; LiteLLM **1.108.8 LTS**
  → compare floor 393; 1.111.0-dev.2 mined for refused-leg billing
  (#50735 → 391) — customer-org budgets / saturation held for stable;
  Grafana cost-split panels converted from watch (392); evening fence
  394. Morning rows 385–389 unchanged (still Filed).

- **2026-11-13 (llama.cpp v1.0.0 + abandoned-work truth)** — Outward:
  **llama.cpp v1.0.0** (first stable major) → MCP cancellation (385) +
  guide/TTS/capacity (388); LiteLLM 1.111.0-dev.1 → abandoned-stream
  (386) + session-pin isolation (387); OpenRouter API changelog
  (guardrail policies → watch). Overnight 341–343 + 345 Shipped;
  fence 389.

- **2026-11-12 pm (LiteLLM 1.108.7 Responses fidelity + CMA recipe)** —
  Outward: **1.108.7 LTS** shipped; mined failed-turn session rebuild
  (#48647 → 380) and Responses-only `max_tool_calls` honesty (#48655 →
  381); Anthropic self-hosted Managed Agents private beta converted
  from watch → recipe (382); compare LTS floor bump (383); evening
  fence (384). Gemini batches / Azure gpt-image edits → watch.
  Verified: `cma-server` metadata already accepted; sequence_number
  pins cover the #44944 class; hygiene floors unchanged.

- **2026-11-12 (billing truth on modality surfaces; LiteLLM security
  night)** — Rows 333/335–338/340 Shipped; restored 370–374 from the
  drained 11-11 pm Actions PR. litellm#51254 → prove-and-fence 378;
  1.108.6 mining → 375/377; images/ASR $0 + `allowed_tools` drop →
  375–377/379. CMA announce → watch (converted pm).

- **2026-11-11 pm → 11-11** — Condensed: coding-router / Gemini 4
  Carbon / daily limits / stream abort (370–374); LiteLLM 1.109.0
  fidelity cut (365–369: `stop_reason`, guardrail surface, streamed
  cache tool_calls, compare + disk-cache positioning).

- **2026-11-09 → 11-10 pm** — Condensed: Kong 2.3.0 (345–349);
  Fable/Mythos 5.2 (350–354); reasoning/BYOK/truncation (355–359);
  residency/auto_caching/5xx/advisor (360–364).

- **2026-11-08 → 11-07** — Condensed: MCP egress + Kong cost (335–344);
  Auto-Router + PG-blip grace + observe/compare (326–334). #2141 needs
  human close.

- **2026-11-06 → 10-28** — Condensed: leaked-key blast radius + Ollama
  0.40.15; TTFT/SLO; governance console; through Apache 2.0 and this
  PRD's creation.
