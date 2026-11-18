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

## Where daari stands (verified in-tree, 2026-11-18 pm)

**Loop velocity.** Afternoon shipped Gemini 4 Carbon + Argon catalog
rates + client credential-field hygiene fence (#2352, #2358).
Overnight 366–368 + 370 still green. Sol promo expires
**2026-11-21 — 3 days** (405 / #2297 still open).

**Outward.** LiteLLM **1.110.0 stable** (Rust-only router, ledger-default
spend, Skills Hub, FIPS, successor alerts, prompt-storage off, typed
overload) still the floor; **1.108.11 LTS**. **1.111.0-rc.1** (same day)
adds Customer Management, default performance alerts (7-day spikes),
dynamic rate limiter + `rate_limited_by`, Gemini 4 Hydrogen catalog,
Microsoft Web IQ `/v1/search`, non-root single image — hold GA claims;
mine what is already public. Portkey 2.33.1, Kong 2.3.1, Ollama
0.40.17-rc1, vLLM 0.34.0, MCP 2026-07-28 flat.

**Inward theme: mine 1.111.0-rc.1 without waiting for GA.** Carbon/Argon
shipped but Hydrogen ($1.50/$7.50 + `xhigh`) is missing (439); no
rolling 7-day performance alerts despite budget/key-expiry webhooks
(440); 429 paths lack a single `rate_limited_by` name (441); compare
must watch RC without promoting the floor (442); afternoon wave is
unit-only (443). Morning 1.110.0 cut (434–438) still open.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 439 | Ship Gemini 4 Hydrogen catalog rates + capabilities + `xhigh` thinking | 4 | 2 | Google AI Studio / LiteLLM 1.111.0-rc.1 day-0 | On-box ledger matches Hydrogen invoice; local tiers still absorb cheap agent loops | Filed [#2359](https://github.com/naveenreddyalka/daari/issues/2359) |
| 440 | On-box performance alerts — spend/traffic/latency/error spikes vs prior 7 days | 4 | 3 | LiteLLM 1.111.0-rc.1 Alerts page (default-on; spike-only) | Same-box ledger already holds every request — no SaaS analytics export | Filed [#2360](https://github.com/naveenreddyalka/daari/issues/2360) |
| 441 | Emit `rate_limited_by` on every 429 naming the limiter that fired | 3 | 2 | LiteLLM 1.111.0-rc.1 dynamic rate limiter header | One process owns every dial; SDKs back off the right local vs frontier cliff | Filed [#2361](https://github.com/naveenreddyalka/daari/issues/2361) |
| 442 | compare-litellm: 1.111.0-rc.1 watch (Customer Mgmt, alerts, Hydrogen); floor stays 1.110.0 / 1.108.11 LTS | 2 | 1 | LiteLLM release notes | Honest RC watch without false GA; Pure-Python router stays the differentiator | Filed [#2362](https://github.com/naveenreddyalka/daari/issues/2362) |
| 443 | Integration fence for the 11-18 afternoon Carbon/Argon + credential-hygiene wave | 2 | 2 | — (testability) | Hermetic proof: Hydrogen-ready Carbon/Argon pins + Azure body-field refuse | Filed [#2363](https://github.com/naveenreddyalka/daari/issues/2363) |
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
| 378 | Prove + fence client credential-field hygiene (immune to the litellm#51254 class); floors 1.109.1/1.108.6 | 3 | 1 | LiteLLM (after its emergency patch) | Allowlist payloads never needed the patch — argue it with a test | Shipped (#2358) |
| 379 | Integration fence for the 11-11/11-12 overnight wave | 2 | 2 | — (testability) | Hermetic proof: MCP egress fidelity, cost split, forensics, patterns | Filed [#2253](https://github.com/naveenreddyalka/daari/issues/2253) |
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Shipped (#2345) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Shipped (#2352) |
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
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **1.111.0-rc.1 remainder** (hold GA:
Customer Management hierarchy UI, dynamic capacity borrow, Web IQ
`/v1/search`, OpenSearch pass-through, per-model tpm/rpm budget maps ≈
open #2240, transcription seconds ≈ #2250, refused-leg #50735 ≈ #2272,
subagent tier-pin #50741 ≈ #2267, encrypted-content #50750); **MCP
file-uploads** draft; Agent Skills Hub (open #1954 adjacency); FIPS
(row 8); per-key/team deployment weights; Switchyard; `latest_turn`
(435 covers stores); empty-output cache #50057 → fold into #2330;
key-expiry emails in-tree (#1546); Opus 4.8 fast-mode removal 11-30;
Ollama 0.40.17-rc1 (MLX concurrent — hold GA); **vLLM 0.34 remainder**;
OpenRouter guardrail-policies API; Kong Cedar/CEL/Token Vault (new dep);
Portkey MCP policies; OpenAI Live/SIP / Realtime/WS; AutoTrust beyond
Apple silicon; `gpt-6-cyber` / `gpt-6-rosalind`; Agents `auto_review`;
Anthropic Compliance API / hosted skills / detector; CMA-as-provider;
minute-grain spend; fleet Redis EWMA; MCP SEP-3398; SCIM + multi-issuer
SSO; A2A 1.1 RC (two-SDK gate). Non-root Docker already `USER daari`.

Verified fine this run — don't re-audit: **response-id ownership +
Responses named-SSE/sequence_number** (1.110.0 parity, never file);
request_log metadata-only (435 reframes stores that hold content);
429/529 transient-classed internally (436 is client envelope);
Carbon/Argon price rows just shipped (#2352); credential hygiene
fence shipped (#2358 — 443 adds gateway hermetic); Opus 4.8 sunset
seeded in #2053; `upstream_retries` (#159) exists — 430 adds http_5xx
isolation.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy truth everywhere money and data move** —
   **Hydrogen catalog (439)**; BYOK modality doors (414); ledger
   credential attribution (415); reconcile under tenancy (416);
   per-tenant zero_retention (435); regional uplift (421); time-bounded
   promo rates before Sol lapses **11-21** (405); refused-leg (391);
   abandoned-stream (386); frontier OCR/image/ASR (396, 375, 376);
   daily `rpd`/`tpd` (372); Grafana input/output (392); tool-fee Prom
   (401); truncation Prom (412). Carbon/Argon (371) shipped.
2. **Honest terminal outcomes end-to-end** — never cache truncated
   turns (424); frontier stream terminal honesty (425); Responses
   `incomplete` (426); typed overload envelopes (436); abort/missing
   `finish_reason` (373); finish_reason Prom (431). Non-stream
   `stop_reason` (365) + streamed cache tool_calls (367) shipped.
3. **Nothing goes stale quietly** — **performance alerts (440)**;
   **`rate_limited_by` (441)**; deprecation successor + exposure (434);
   any-5xx doctor + Prom (429–430); auto_caching doctor + Prom
   (419–420); MCP egress re-mint (395); modality deadlines (400);
   MCP cancellation (385); session-pin isolation (387); ZDR (398);
   reservation doctor tip (403).
4. **Agent-loop / Responses / Extractions fidelity + CMA** —
   Responses output-order + reasoning (406); local-tier thinking (407);
   Extractions (390); OpenRouter `reasoning` (397); failed
   `previous_response_id` (380); `max_tool_calls` (381);
   `allowed_tools` (377); Managed Agents recipe (382). Tool_call-arg
   (366) + coding-router (370) + credential hygiene (378) shipped.
5. **Local engine floor + survive the blip + honest compare** —
   **1.111.0-rc.1 watch (442)**; LiteLLM floor **1.110.0 / 1.108.11
   LTS** (437); vLLM 0.34.0 pin (427); watermark docs (433); HF /
   scoped-keys (432); llama.cpp v1.0.0 (388); binding Prom (417);
   stream_fallback Grafana (410); offline Prom/doctor (279/285);
   reservation Grafana (402); hot-reload (6); failover panels (274);
   fences through 443; then 62–67.

---

## Changelog

- **2026-11-18 pm (1.111.0-rc.1 mined; Carbon/Argon shipped)** —
  Afternoon #2352 / #2358. Mined RC without promoting the floor:
  Hydrogen catalog + `xhigh` (439), 7-day performance alerts (440),
  `rate_limited_by` (441), compare RC watch (442), afternoon fence
  (443). Hold Customer Management UI / Web IQ / capacity-borrow for
  GA. Sol still 3 days out (#2297).

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
