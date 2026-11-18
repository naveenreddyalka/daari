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

## Where daari stands (verified in-tree, 2026-11-18)

**Loop velocity.** Overnight shipped 366–368 + 370 (#2342–#2345):
tool_call-argument guardrails, L0 tool_calls cache exclusion,
1.109.0 compare floor, coding-router recipe. Sol promo expires
**2026-11-21 — 3 days** (405 / #2297 still open).

**Outward.** **LiteLLM v1.110.0 went STABLE 11-18 01:36 UTC** — the
Python router core is deleted (Rust core only), SpendLogs ledger is
the default accounting path, Agent Skills Hub, FIPS mode,
deprecation alerts with `successor_model` + per-key daily requests,
per-key/team prompt-storage off, typed overload envelopes
(503 `server_is_overloaded` / 529 `overloaded_error`). **1.108.11
is the live LTS** (11-17); 1.111.0-rc.1 cut 11-18 (hold for
stable). Portkey 2.33.1, Kong 2.3.1, Ollama 0.40.17-rc1, vLLM
0.34.0, MCP spec 2026-07-28 all flat.

**Inward theme: mine 1.110.0 stable.** Lifecycle has zero
`successor` handling and no tenant exposure report (434); no
per-key/team `zero_retention` dial though prompts persist in the
responses store `_conversation` and cache puts (435); exhausted
429/529 collapses to a generic 503 string with no typed envelope
or Retry-After (436); compare floor is a day stale again (437);
the overnight wave is unit-only (438).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 434 | Lifecycle `successor_model` + `deprecation_source` + per-key/team deprecation exposure report from the on-box ledger | 3 | 2 | LiteLLM 1.110.0 (`successor_model`, alerts w/ daily requests by key, owner emails) | Ledger already holds per-tenant model usage — exposure report is one local query, no email infra, nothing leaves the box | Filed [#2346](https://github.com/naveenreddyalka/daari/issues/2346) |
| 435 | Per-key/team `zero_retention` dial — tenant prompt content persists in responses-store `_conversation` + L0/org/semantic cache puts with no opt-out | 4 | 3 | LiteLLM 1.110.0 per-key/team prompt-storage off + `latest_turn` | One box owns every store; "no tenant bytes at rest" is enforceable and provable at one edge (distinct from 398's provider-side ZDR) | Filed [#2347](https://github.com/naveenreddyalka/daari/issues/2347) |
| 436 | Typed overload envelopes: exhausted 429/529 answers generic 503 string — no `server_is_overloaded` / `overloaded_error`, no Retry-After | 3 | 2 | LiteLLM 1.110.0 (503 typed + faithful 529 on /v1/messages) | Router already classifies overload internally (circuit breaker skips 429/529) — surface the same truth so SDK backoff works against local tiers too | Filed [#2348](https://github.com/naveenreddyalka/daari/issues/2348) |
| 437 | compare-litellm: 1.110.0 stable floor + 1.108.11 LTS; Rust-only router (Python core deleted) + ledger-default positioning | 2 | 1 | LiteLLM release notes | Pure-Python single-process router stays pdb-debuggable and on-site patchable; honest floors keep the compare credible | Filed [#2349](https://github.com/naveenreddyalka/daari/issues/2349) |
| 438 | Integration fence for the 11-17/11-18 overnight guardrails + L0 tool_calls + coding-router wave | 2 | 2 | — (testability) | Hermetic proof: tool_call-arg block, L0 miss on tool_calls, doctor recipe finding | Filed [#2350](https://github.com/naveenreddyalka/daari/issues/2350) |
| 429 | Doctor tip when `upstream.retry.failover_on_http_5xx` is on — silent today while peer dials already tip | 2 | 1 | — (ops honesty) | Single-box preflight before broad 5xx hopping burns retries on permanent 501s | Filed [#2336](https://github.com/naveenreddyalka/daari/issues/2336) |
| 430 | Prom/stats for http_5xx failover hops by status — `upstream_retries` does not isolate the Kong-style dial | 3 | 2 | Kong AI Gateway FinOps / Portkey analytics | Prove dial pressure from the same-box scrape; local legs stay flat | Filed [#2337](https://github.com/naveenreddyalka/daari/issues/2337) |
| 431 | Prom/stats for `finish_reason` / `stop_reason` outcomes (`stop`, `length`, `pause_turn`, `refusal`, `tool_calls`) | 3 | 2 | LiteLLM spend dashboards / Portkey | Outcome pressure next to cache + spend on one scrape across local + frontier | Filed [#2338](https://github.com/naveenreddyalka/daari/issues/2338) |
| 432 | compare-openrouter: HF Inference Providers routing + scoped management keys (11-16 announcements) | 2 | 1 | OpenRouter announcements | Honest marketplace vs on-box positioning; session pins ≈ HF affinity without claiming HF broker | Filed [#2339](https://github.com/naveenreddyalka/daari/issues/2339) |
| 433 | Claude text-watermark sampling caveat — six-model list + daari omit-inject honesty (no detector claim) | 3 | 1 | Anthropic text-watermark docs | Compliance buyers see omit-inject as the local-first guarantee; detection stays Anthropic-side | Filed [#2340](https://github.com/naveenreddyalka/daari/issues/2340) |
| 424 | Never cache truncated/paused/refused turns — L0/L1/org/agent-prefix puts gate on tier+content only, not `finish_reason`; L0 stream replay even rewrites to `stop` | 4 | 2 | — (GPTCache/LiteLLM cache blindly too) | The $0 cache tier is the headline; a hit must always be a complete turn or agent loops can't trust it | Filed [#2330](https://github.com/naveenreddyalka/daari/issues/2330) |
| 425 | Frontier streamed legs surface honest `finish_reason` — `frontier.stream()` yields text only; terminal chunks hardcode `stop`/`tool_calls` (local streams already honest) | 4 | 3 | LiteLLM / OpenRouter relay upstream finish_reason verbatim | One box fronts local + frontier; truncation honesty must survive the stream abstraction on the legs that cost money | Filed [#2331](https://github.com/naveenreddyalka/daari/issues/2331) |
| 426 | `/v1/responses` honest `status: "incomplete"` + `incomplete_details` (`max_output_tokens` / `content_filter`) — today every build hardcodes `completed` | 4 | 2 | OpenAI native; LiteLLM bridge relays it | Local tiers truncate too (`num_predict`); one honest incomplete contract across local + frontier, durable in the on-box store | Filed [#2332](https://github.com/naveenreddyalka/daari/issues/2332) |
| 427 | vLLM 0.34.0 GA refresh: upgrade traps (MRV2-only, block-size 64, extensible KV cache default, ROCm 10), local ASR models, Ripple-on-vLLM note | 3 | 1 | vLLM release docs | daari is the governance layer on the engine; honest floors + upgrade traps keep "your own vLLM behind daari" credible | Filed [#2333](https://github.com/naveenreddyalka/daari/issues/2333) |
| 428 | Integration fence for the 11-16/11-17 overnight 5xx-failover + advisor-gate + stop_reason wave | 2 | 2 | — (testability) | Hermetic proof: 501/522 dial on/off, advisor 400 copy, stop_reason round-trip | Filed [#2334](https://github.com/naveenreddyalka/daari/issues/2334) |
| 419 | Doctor tip when `frontier.auto_caching` is on without an Anthropic-capable L6 slot | 3 | 1 | — (ops honesty) | Single-box preflight catches a silent no-op cache dial | Filed [#2321](https://github.com/naveenreddyalka/daari/issues/2321) |
| 420 | Prom/stats counters for auto_caching applied vs client-preserved (Anthropic L6 only) | 3 | 1 | Portkey analytics / hand-rolled Prom | Same-box scrape proves cache-write pressure without exporting prompts | Filed [#2322](https://github.com/naveenreddyalka/daari/issues/2322) |
| 421 | Prom/stats for OpenAI regional-processing 1.10× uplift by region (incl. CA/SG/KR/GB/AE) | 3 | 1 | Kong AI Gateway FinOps / Portkey | Prove residency invoice math from the scrape; local legs stay 0 | Filed [#2323](https://github.com/naveenreddyalka/daari/issues/2323) |
| 422 | compare-litellm: LTS floor → 1.108.10; wildcard `base_model` pricing + PDF-URL async notes | 3 | 1 | LiteLLM 1.108.10 release notes | Honest floor + on-box ledger already bills the served model | Filed [#2324](https://github.com/naveenreddyalka/daari/issues/2324) |
| 423 | Integration fence for the 11-16 afternoon auto_caching + residency + LTS-floor wave | 2 | 2 | — (testability) | Hermetic proof: inject/preserve/non-leak, 1.10× pins, compare floor | Filed [#2325](https://github.com/naveenreddyalka/daari/issues/2325) |
| 414 | Team/key BYOK must sign the modality + passthrough L6 doors (images, ASR, OCR, moderations, rerank, decisions) — binding and pool pin currently ignored there | 4 | 3 | LiteLLM per-deployment keys / Kong upstream credentials | Tenant credential everywhere money moves, enforced at one box's edge; local legs stay $0 | Filed [#2313](https://github.com/naveenreddyalka/daari/issues/2313) |
| 415 | Spend ledger records `credential_source` (global/team/key) + frontier slot on every billed row; `daari report` split | 4 | 2 | LiteLLM key-alias spend tags; Kong AI Gateway FinOps | Same-box ledger mirrors each provider invoice without SaaS export | Filed [#2314](https://github.com/naveenreddyalka/daari/issues/2314) |
| 416 | Analytics reconcile excludes tenant-credential spend (false drift vs global-org analytics after BYOK) | 3 | 2 | — (no gateway ships ledger-vs-invoice drift detection) | On-box billing truth stays honest under multi-credential tenancy | Filed [#2315](https://github.com/naveenreddyalka/daari/issues/2315) |
| 417 | Prom/stats counters for frontier binding outcomes (signed / pin_unmatched / unresolvable incl. fail-closed 502) | 2 | 1 | Portkey analytics / hand-rolled Prom | Same-box scrape proves tenant isolation without exporting tenant traffic | Filed [#2316](https://github.com/naveenreddyalka/daari/issues/2316) |
| 418 | Integration fence for the 11-15/11-16 overnight team-BYOK + Ripple wave | 2 | 2 | — (testability) | Hermetic proof: binding precedence, fail-closed 502, redaction, doctor, recipe | Filed [#2317](https://github.com/naveenreddyalka/daari/issues/2317) |
| 409, 411 | `stream_fallback_continue` refuses after delivered tool_calls; doctor tip for the dial | 2–5 | 1–2 | LiteLLM 1.111-dev #51683 | Local agent loops must not double-fire shell tools across a midstream hop | Shipped (#2309, #2310) |
| 410 | Grafana panel for `daari_stream_fallback_continue_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Same-box scrape shows whether the opt-in dial is firing | Filed [#2304](https://github.com/naveenreddyalka/daari/issues/2304) |
| 412 | Prom/stats counters for Responses `truncation` auto + rejected | 3 | 1 | LiteLLM spend dashboards / Kong FinOps | Prove the just-shipped dial from the same-box scrape | Filed [#2306](https://github.com/naveenreddyalka/daari/issues/2306) |
| 413 | Integration fence for the 11-15 evening truncation + midstream-safety wave | 2 | 2 | — (testability) | Hermetic proof: tool-call refuse, Grafana, doctor, truncation counters | Filed [#2307](https://github.com/naveenreddyalka/daari/issues/2307) |
| 405 | Time-bounded catalog rates: `effective_to` promo windows + baseline fallback (Sol $4/$20 → $5/$30 on 11-21; Gemini 12-01 step-up class) | 4 | 2 | Kong 2.3.0 dynamic-pricing `effective_to`/`baseline_price` | Honest ledger through published price changes with no redeploy and no SaaS price feed | Filed [#2297](https://github.com/naveenreddyalka/daari/issues/2297) |
| 406 | Preserve every reasoning item + upstream output order on the frontier Responses path | 4 | 3 | LiteLLM 1.108.9 LTS (#51356 backport) | Byte-faithful item order on one box fronting local + frontier; encrypted replay keeps positional binding | Filed [#2298](https://github.com/naveenreddyalka/daari/issues/2298) |
| 407 | Surface local-tier thinking: capture Ollama `message.thinking` / OpenAI-compat `reasoning_content`, emit on chat + Responses + Messages | 4 | 3 | llama.cpp / vLLM emit it; LiteLLM relays it (1.108.9 #51748) | Local reasoning models are the pitch — daari pays the thinking tokens and must stop discarding the text | Filed [#2299](https://github.com/naveenreddyalka/daari/issues/2299) |
| 408 | Integration fence for the 11-14/11-15 overnight wave | 2 | 2 | — (testability) | Hermetic proof: thinking strip, toolset gate, baggage PATCH, encrypted reasoning | Filed [#2300](https://github.com/naveenreddyalka/daari/issues/2300) |
| 400 | Honor `X-Daari-Deadline-Ms` / `request_deadline_seconds` on OCR + image routes | 3 | 2 | LiteLLM 1.111-dev `total_timeout` (proxy-wide) | One dial aborts every modality on-box; local vision OCR still $0 under the budget | Filed [#2287](https://github.com/naveenreddyalka/daari/issues/2287) |
| 401 | Prometheus counters for server-side tool fee USD by tool type | 3 | 2 | Kong AI Gateway FinOps tool-category spend | Same-box scrape next to input/output USD; $0 tools stay flat | Filed [#2288](https://github.com/naveenreddyalka/daari/issues/2288) |
| 402 | Grafana panel for `daari_budget_reservation_denied_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Pre-charge 402 pressure on the overview next to frontier spend | Filed [#2289](https://github.com/naveenreddyalka/daari/issues/2289) |
| 403 | Doctor tip: `budgets.reserve_in_flight` on without USD budget windows | 2 | 1 | — (ops honesty) | Catch silent no-op pre-charge before production traffic | Filed [#2290](https://github.com/naveenreddyalka/daari/issues/2290) |
| 404 | Integration fence for the 11-14 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: modality deadline, tool-fee Prom, reservation panel, doctor tip | Filed [#2291](https://github.com/naveenreddyalka/daari/issues/2291) |
| 395 | MCP egress must re-resolve `secret://` tokens near use (expired oauth re-mint) | 4 | 2 | LiteLLM 1.106.10 (#41197 backport) | Resident single-box daemon must not go stale after `expires_in`; refresh machinery already proven on the frontier pool | Filed [#2281](https://github.com/naveenreddyalka/daari/issues/2281) |
| 396 | Bill the frontier OCR leg (`mistral-ocr-latest` per-page); local/vision stay $0 | 4 | 2 | Mistral per-page billing; LiteLLM catalog | The leg that costs money is the leg the same-box ledger must meter; closes an OCR budget bypass | Filed [#2282](https://github.com/naveenreddyalka/daari/issues/2282) |
| 397 | Honor the OpenRouter `reasoning` object on chat/completions (effort/max_tokens/exclude/enabled) | 3 | 2 | OpenRouter (Nov-11 diff adds context/enabled/exclude/mode) | Drop-in base-URL migration keeps reasoning controls; local tiers honor them at $0 | Filed [#2283](https://github.com/naveenreddyalka/daari/issues/2283) |
| 398 | ZDR honesty: retention-required Claude models never serve `provider.zdr` requests | 3 | 2 | — (no gateway does model-level retention gating) | L1–L5 are trivially zero-retention; be honest about the frontier exception instead of silently breaking compliance pins | Filed [#2284](https://github.com/naveenreddyalka/daari/issues/2284) |
| 399 | Integration fence for the 11-13/11-14 overnight wave | 2 | 2 | — (testability) | Hermetic proof: tool fees, reservation deny/release, key label, 5.2 rates | Filed [#2285](https://github.com/naveenreddyalka/daari/issues/2285) |
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
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Shipped (#2345) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Filed [#2239](https://github.com/naveenreddyalka/daari/issues/2239) |
| 372 | Per-model daily `rpd`/`tpd` + virtual-model failover on exhaust | 3 | 2 | LiteLLM 1.109.0 deployment daily limits | Burn one L6 daily quota; walk continues on local peers | Filed [#2240](https://github.com/naveenreddyalka/daari/issues/2240) |
| 373 | Streams that `abort` or omit `finish_reason` fail visibly + failover | 4 | 2 | LiteLLM 1.109.0 stream-failure visibility | On-box failover salvages cancelled/truncated turns | Filed [#2241](https://github.com/naveenreddyalka/daari/issues/2241) |
| 374 | Integration fence for the 11-11 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: coding compose, Carbon rates, daily skip, abort | Filed [#2242](https://github.com/naveenreddyalka/daari/issues/2242) |
| 365–368 | Honest `stop_reason`; tool_call-arg guardrails; L0 keeps/excludes `tool_calls`; 1.109.0 compare floor | 3–4 | 1–2 | LiteLLM 1.109.0 fixes | Truncation + secret honesty on one box | Shipped (#2329, #2342–#2344) |
| 369 | Integration fence for the 11-10/11-11 overnight wave | 2 | 2 | — (testability) | Hermetic proof: cost-aware selection prefers $0 local; SLO panel pinned | Filed [#2236](https://github.com/naveenreddyalka/daari/issues/2236) |
| 360–361 | Residency CA/SG/KR/GB/AE 1.10×; Anthropic auto_caching | 2–3 | 1–2 | OpenAI / Portkey 2.33.0 | Governance + cache dials on the same-box console | Shipped (#2319, #2320) |
| 362–363 | any-5xx failover; Fable/Mythos 5.2 advisor gate | 2–3 | 1–2 | Kong 2.3.0 / Anthropic | Failover + advisor honesty | Shipped (#2327, #2328) |
| 364 | Integration fence for the 11-10 evening residency/caching/failover wave | 2 | 2 | — (testability) | Hermetic proof of that wave's dials | Filed [#2224](https://github.com/naveenreddyalka/daari/issues/2224) |
| 356 | Responses `truncation` auto/disabled | 3 | 2 | LiteLLM 1.108.4 | On-box compact vs honest 400 against serving window | Shipped (#2302) |
| 357–358 | Team BYOK; Ripple recipe | 2–4 | 1–3 | Ollama 0.40.16 | Tenant + local catalog on-box | Shipped (#2311, #2312) |
| 359 | Integration fence for the 11-09/11-10 overnight wave | 2 | 2 | — (testability) | Hermetic proof of that wave's governance dials | Filed [#2218](https://github.com/naveenreddyalka/daari/issues/2218) |
| 351–353, 355 | 5.2 thinking strip on failover; computer-toolset gate; `baggage_to_tags` PATCH; encrypted reasoning on `/v1/messages` | 3–4 | 1–2 | Anthropic 11-09 gates / LiteLLM 1.108.4 | Switch-owned strip + reasoning fidelity on-box | Shipped (#2293–#2296) |
| 346–348, 350 | Server-side tool billing + `tool_usage`; in-flight reservation; per-key Prom label; 5.2 catalog rates | 3–4 | 2–3 | Kong 2.3.0 / Anthropic list prices | FinOps truth on the same-box ledger and scrape | Shipped (#2277–#2280) |
| 354 | Integration fence for the 11-09 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: baggage tags, service-tier Grafana, 5.2 catalog smoke | Filed [#2208](https://github.com/naveenreddyalka/daari/issues/2208) |
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
(`io.modelcontextprotocol/files` — no reference impl; ~EOY);
**LiteLLM 1.110.0 stable mined this run (434–437)** — remainder on
watch: Agent Skills Hub (open #1954 adjacency), FIPS mode (row 8),
per-key/team deployment weights (tiers ≠ deployments; buyer ask),
Switchyard stage router, `latest_turn` spend-log mode (435 covers
the stores that matter), empty-output cache gate #50057 (fold into
open #2330 — same put sites); **1.111.0-rc.1** (hold for stable:
per-model tpm/rpm budget maps ≈ open #2240, principal-attribute
access groups, OpenSearch pass-through, customer portal beta,
transcription seconds billing ≈ open #2250, refused-leg billing
#50735 ≈ open #2272, subagent tier-pin isolation #50741 ≈ open
#2267, encrypted-content boundary #50750); key-expiry emails
already in-tree (#1546); 1.108.7/1.109 remainder (buyer-ask
batches/edits; K8s discovery; shadow rates); Opus 4.8
fast-mode removal 11-30; Ollama 0.40.17-rc1 (MLX concurrent — hold
for GA); **vLLM 0.34 remainder** (checkpoint/restore ops recipe,
cache-aware admission lever, Mistral Large 4 / MiniMax-M3.1 — buyer
ask; 427 covers docs); **OpenRouter guardrail-policies API**;
OpenRouter newest (`ContentFilterReadEntry`, Responses `error_data`,
`catalog_index_note`, `web_fetch.retrieved_at`, OTEL `metricsEndpoint`
— metrics already in-tree); LTS floor **1.108.10** (422); Kong
Cedar/CEL/Token Vault (new dep — human); Portkey MCP policies
(Prisma AIRS-only); OpenAI Live/SIP / Realtime/WS; AutoTrust beyond
Apple silicon; `gpt-6-cyber` / `gpt-6-rosalind`; Agents `auto_review`;
Anthropic Compliance API / hosted skills / detector (private
preview); CMA-as-provider; minute-grain spend; fleet Redis EWMA; MCP
SEP-3398; OpenAI org external keys; `between_tools`; Claude Code
`groups` / `guardrail_trace`; OpenRouter private-provider CRUD;
LiteLLM Admin Chat / Lens / ID-JAG; llama.cpp `/v1/realtime`; Portkey
JWT/WIF; Prisma AIRS Agent Identity; Claude-on-GCP IAM (new dep);
Open Responses WS; Prom exemplars + `gen_ai.agent.*`; SCIM +
multi-issuer SSO; Kong Skills/A2A; certifi emSign; Ollama d1 GA;
local message-thread analogue (after ask); A2A 1.1 RC (two-SDK gate).

Verified fine this run — don't re-audit: **response-id ownership
already gated** (response_store `owner_key_id` +
`response_visible_to_caller` + tenancy-denied audit on both
`previous_response_id` paths, responses.py ~L1013/~L1228 — LiteLLM
1.110.0 #49402 parity exists, never file); **Responses named-SSE
framing + `sequence_number` + `id:` resume already emitted**
(`_sse_with_sequence` responses.py ~L600 — their #47980/#44944
parity, never file); request_log is metadata-only (no prompt
content — 435 reframes prompt-storage-off onto the stores that
hold content); 429/529 already transient-classed internally
(circuit_breaker.py L19–25; 436 is the client envelope only);
Opus 4.8 sunset seeded in #2053; `upstream_retries` (#159) exists
— 430 adds http_5xx isolation, not a duplicate.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy truth everywhere money and data move** —
   BYOK modality doors (414); ledger credential attribution (415);
   reconcile under tenancy (416); **per-tenant zero_retention
   (435)**; regional uplift on the scrape (421); time-bounded promo
   rates before Sol lapses **11-21** (405); refused-leg sum (391);
   abandoned-stream settlement (386); frontier OCR/image/ASR (396,
   375, 376); Gemini 4 Carbon/Argon (371); daily `rpd`/`tpd` (372);
   Grafana input/output (392); tool-fee Prom (401); truncation Prom
   (412).
2. **Honest terminal outcomes end-to-end** — never cache truncated
   turns (424); frontier stream terminal honesty (425); Responses
   `incomplete` status (426); **typed overload envelopes (436)**;
   abort/missing `finish_reason` (373); finish_reason Prom (431).
   Non-stream `stop_reason` (365) + streamed cache tool_calls
   (367) shipped.
3. **Nothing goes stale quietly** — **deprecation successor +
   exposure report (434)**; any-5xx doctor + Prom (429–430);
   auto_caching doctor + Prom (419–420); MCP egress re-mint (395);
   modality deadlines (400); MCP cancellation (385); session-pin
   isolation (387); ZDR (398); reservation doctor tip (403).
4. **Agent-loop / Responses / Extractions fidelity + CMA** —
   Responses output-order + reasoning items (406); local-tier
   thinking (407); Extractions (390); OpenRouter `reasoning` (397);
   failed `previous_response_id` (380); `max_tool_calls` (381);
   `allowed_tools` (377); Managed Agents recipe (382); credential
   hygiene fence (378). Tool_call-arg scan (366) + coding-router
   (370) shipped.
5. **Local engine floor + survive the blip + honest compare** —
   LiteLLM floor **1.110.0 / 1.108.11 LTS** (437); vLLM 0.34.0 pin
   (427); watermark omit-inject docs (433); HF / scoped-keys
   compare (432); llama.cpp v1.0.0 pin (388); LTS floor 1.108.10
   (422, supersede with 437); binding Prom (417); stream_fallback
   Grafana (410); offline Prom/doctor (279/285); reservation
   Grafana (402); hot-reload (6); failover panels (274); fences
   through 438; then 62–67.

---

## Changelog

- **2026-11-18 (LiteLLM 1.110.0 stable mined)** — 1.110.0 stable
  (Rust-only router, ledger-default accounting, Skills Hub, FIPS)
  + 1.108.11 LTS + 1.111.0-rc.1 overnight. Verified fine:
  response-id ownership + named-SSE/sequence_number already in-tree.
  Filed: lifecycle successor + exposure report (434), per-tenant
  zero_retention (435), typed overload envelopes (436), compare
  1.110.0 floor (437), overnight fence (438). Overnight 366–368 +
  370 Shipped (#2342–#2345).

- **2026-11-17 (+pm)** — Condensed: vLLM 0.34.0 GA mined; truncation
  honesty 424–428; pm prove-the-dials 429–433; watermark six-model
  caveat; 362–363 + 365 Shipped.

- **2026-11-16 → 11-14** — Condensed: auto_caching + residency ops
  (419–423); team-BYOK follow-through (414–418); midstream
  tool-call safety (409–413); LiteLLM 1.108.9 mined (406–408);
  MCP re-mint + OCR + reasoning + ZDR + deadlines (395–404).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg /
  llama.cpp v1.0.0 (385–394); CMA + 1.108.6/7 (375–384);
  coding-router / Gemini 4 / daily limits (370–374); Kong 2.3.0 /
  Fable 5.2 / MCP egress / Auto-Router through Apache 2.0 and this
  PRD's creation. #2141 needs human close.
