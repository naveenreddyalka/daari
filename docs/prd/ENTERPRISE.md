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

## Where daari stands (verified in-tree, 2026-11-21)

**Loop velocity.** Overnight shipped the 11-13 band's last four:
MCP `notifications/cancelled` (#2398), abandoned-frontier-stream
ledger settle (#2399), conversation-prefix session pins (#2400),
llama.cpp v1.0.0 guide (#2401) — issues #2265–#2268. The 11-20 pm
filings 459–463 and morning 454–458 remain open.

**Outward.** **Anthropic linked billing beta (11-17, surfaced
11-20):** platforms set `billing_policy` per `/v1/messages` or
`/v1/chat/completions` request under `user-profiles-billing-2026-10-01`;
Anthropic bills the end customer's org directly; unbillable
customer-paid requests are refused, never platform-billed. SDK
2.12.0 moves `user_profile_id` into the body on Bedrock. **OpenAI
changelog amended 11-21: new models will never support Flex**; the
beta winds down on supported ones. **LiteLLM 1.108.14 LTS (11-20
night):** Claude server-tool declarations lost on `/v1/responses`
follow-ups → Anthropic 400s (#50821); `input_json` parts on
`/v1/decisions` (#52807 — daari already parses them). **Ollama
0.40.17 GA:** tool definitions keep unmodeled JSON-schema keywords,
`ollama launch claude` deferred tool loading, Apple-silicon
concurrency, Inkling 2 Mini (Apple-only). Kong 2.3.2 = nginx CVEs.
Portkey 2.33.1 / vLLM 0.34.0 / OpenRouter (11-19) / MCP blog flat.

**Inward theme: the facade and the bill-payer are the day's truth
gaps.** The Ollama facade drops `tools` entirely (`extra="ignore"`,
no field — tool clients silently break, 467); `billing_policy` is
dropped on the rebuilt Anthropic body and the ledger has no bill-to
dimension (465); `pricing.py` applies the 0.5 flex factor on the
tier string alone while Flex winds down (466); the flattened
`_conversation` replay wants a #50821-class fence (464); overnight
wave unfenced (468).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 464 | Prove + fence: `previous_response_id` follow-ups never replay undeclared server-tool blocks (litellm #50821, fixed in 1.108.14 LTS) | 3 | 1 | LiteLLM (after its LTS patch) | Flattened `_conversation` replay makes the 400 class structurally impossible — argue it hermetically | Filed [#2402](https://github.com/naveenreddyalka/daari/issues/2402) |
| 465 | Anthropic linked billing — forward `billing_policy` (dropped by the rebuilt Messages body today); ledger bill-to dimension; customer-paid legs out of org budgets + reconcile | 4 | 2 | Anthropic native (platform-side); no gateway relays it yet | daari is the platform in Anthropic's model; one on-box ledger tells platform-paid from customer-paid (adjacent to 415/416 credential attribution) | Filed [#2403](https://github.com/naveenreddyalka/daari/issues/2403) |
| 466 | Flex wind-down: capability-gate `service_tier=flex` (new models never get Flex, changelog 11-21); `pricing.py` 0.5 factor keyed on tier string alone misprices non-Flex models | 3 | 1 | OpenAI changelog / LiteLLM cost map | Capability + price fence is one catalog entry in one process; degrade with `dropped_params` honesty (6.2 refuse case shared with 452) | Filed [#2404](https://github.com/naveenreddyalka/daari/issues/2404) |
| 467 | Ollama facade tool calling — `/api/chat` has no `tools` field (`extra="ignore"`); tool clients (`ollama launch claude`/opencode, 0.40.17) silently lose tools through daari | 4 | 2 | Ollama native 0.40.17 (keeps unmodeled schema keywords) | Facade puts cache + per-key tool governance in front of every Ollama-wire client — only if the tool loop survives the hop | Filed [#2405](https://github.com/naveenreddyalka/daari/issues/2405) |
| 468 | Integration fence for the 11-20/11-21 overnight MCP-cancel + abandoned-stream ledger + session-pin wave | 2 | 2 | — (testability) | Hermetic proof: cancelled relays, partial usage settles, prefix scopes the pin | Filed [#2406](https://github.com/naveenreddyalka/daari/issues/2406) |
| 459 | Deferred tool schema protocol — honor `defer_loading` + `tool_search` / OpenRouter `deferred_tools` on Responses + Messages (hide until search loads; `scope` all\|mcp) | 4 | 3 | OpenRouter Tool Search beta / Gemini Tool Retrieval preview | Large MCP catalogs stay $0 tokens on local legs; one edge owns deferral + grants without a SaaS tool broker | Filed [#2392](https://github.com/naveenreddyalka/daari/issues/2392) |
| 460 | Sol promo end-date honesty — official end is **2026-11-30** not 11-21; keep $4/$20 until then; align settings comments, budgets-frontier, effective_to AC | 3 | 1 | OpenAI pricing page (checked 11-20) | Ledger must not step up a week early or leave stale “expires tomorrow” ops copy | Filed [#2393](https://github.com/naveenreddyalka/daari/issues/2393) |
| 461 | GPT-Live-1.1 (+ gpt-live-1 standby) catalog — $0.05/min active, $0.02/min standby; capabilities note; no full `/v1/live` WS yet | 3 | 2 | OpenAI Live pricing / LiteLLM cost-map #52926 | Same-box duration ledger when Live eventually fronts; local voice stays $0 until then | Filed [#2394](https://github.com/naveenreddyalka/daari/issues/2394) |
| 462 | Prove + fence: USD-exhausted keys still reach `/v1/models` + count_tokens (litellm #51675 class) | 3 | 1 | LiteLLM (after #51675) | Agents diagnose spend cliffs without a discovery blackout on one box | Filed [#2395](https://github.com/naveenreddyalka/daari/issues/2395) |
| 463 | Prove + fence: Anthropic `/v1/messages` bills on-box catalog rates when client forwards Anthropic credentials (litellm #52313 class) | 4 | 2 | LiteLLM 1.110.2 / 1.112-dev (#52313) | Tenant BYOK never zeros the org ledger; invoice math stays on-box | Filed [#2396](https://github.com/naveenreddyalka/daari/issues/2396) |
| 454 | Fable/Mythos 5.1+5.2 param_compat — strip temperature/top_p/top_k (defaults included), never emit `thinking: disabled`/`budget_tokens` on 5.2, degrade forced tool_choice `any`/`tool` | 5 | 2 | LiteLLM 1.110.2 (regression-fixed #52341) / Anthropic migration guide | One declared constraint family at the edge for the flagship Anthropic models; operators hotfix via `frontier.param_compat`, no backport night | Filed [#2384](https://github.com/naveenreddyalka/daari/issues/2384) |
| 455 | GPT-6.2 chat-leg prompt cache — `_build_messages` keeps `role: system` verbatim; 6.2 needs `developer` on /chat/completions + Messages bridge (litellm #52906, all five lines) | 4 | 2 | LiteLLM 11-20 backports / OpenAI caching guide | Escalated repeats must bill cached ($0.40/M) not list ($8/M); L0–L5 absorb the rest at $0. Adjacent to 451 (#2376, Responses placement) | Filed [#2385](https://github.com/naveenreddyalka/daari/issues/2385) |
| 456 | Scope `POST /introspect` — any virtual key can introspect any token today (team names, quotas, master-key oracle); self-introspect only (litellm #52838 /key/info class) | 3 | 1 | LiteLLM (after its four-line backport) | Tenant isolation at one box's edge includes the introspection door; RFC 7662-safe deny + audit event | Filed [#2386](https://github.com/naveenreddyalka/daari/issues/2386) |
| 457 | Prove + fence no-duplicate stream delivery — buffer-then-flush, relay prefetch, fail-closed continue (litellm #52461/#52616 retried delivered streams; double billing) | 3 | 1 | — (daari immune by construction; litellm patched reactively) | "Never the same delta twice, never a restarted bill" provable hermetically on one box | Filed [#2387](https://github.com/naveenreddyalka/daari/issues/2387) |
| 458 | Integration fence for the 11-19/11-20 overnight ASR-billing, allowed_tools, failed-chain, max_tool_calls wave | 2 | 2 | — (testability) | Hermetic proof: ASR ledger row, allowed_tools both layouts, poison-chain reject, dropped_params honesty | Filed [#2388](https://github.com/naveenreddyalka/daari/issues/2388) |
| 449 | GPT-6.2 param_compat — strip temperature/top_p/logprobs, floor effort `none`→`low`, `tools_transport=responses` | 5 | 1 | OpenAI migration guide / LiteLLM GPT-6 family table | One Pure-Python table at the edge; local tools stay $0; frontier never sees a forbidden chat+tools shape | Filed [#2374](https://github.com/naveenreddyalka/daari/issues/2374) |
| 450 | GPT-6.2 Ultrafast allowlist + 3× promo factor through 2027-02-28 (then 6×); EU Astra still unsupported | 4 | 2 | OpenAI Ultrafast pricing | Same-box multiplier matches invoice without a SaaS price feed; local legs stay 1.0× | Filed [#2375](https://github.com/naveenreddyalka/daari/issues/2375) |
| 451 | GPT-6.2 `store:false` prompt-cache placement — leading `developer` in `input`, not trailing `instructions` (LiteLLM 1.110.1 class) | 4 | 2 | LiteLLM 1.110.1 / OpenAI caching guide | Encrypted-reasoning Responses hop already owns the wire; fix once, every L6 escalate caches | Filed [#2376](https://github.com/naveenreddyalka/daari/issues/2376) |
| 452 | Responses background `completion_window` discounts (2h −30%, 8h −40%); refuse Flex on GPT-6.2 | 3 | 2 | OpenAI 11-17 changelog | Background that stays local is $0; escalated jobs must meter the published window | Filed [#2377](https://github.com/naveenreddyalka/daari/issues/2377) |
| 453 | Integration fence for the 11-19 pm GPT-6.2 follow-through + frontier image-billing wave | 2 | 2 | — (testability) | Hermetic proof: param_compat, Ultrafast, developer placement, window discount, image spend | Filed [#2378](https://github.com/naveenreddyalka/daari/issues/2378) |
| 444 | GPT-6.2 Astra + Sol catalog rates + capabilities + 12h cache-write billing (launched 11-17) | 4 | 2 | OpenAI pricing / LiteLLM same-night backports across 4 lines | Flagship L6 pin bills honestly from the same-box ledger on day 0 — no emergency backport wave | Filed [#2367](https://github.com/naveenreddyalka/daari/issues/2367) |
| 445 | Relay MCP Events Extension (SEP-3415, merged 11-19): advertise upstream `extensions`, relay events/list + events/poll under MCP grants | 4 | 3 | — (spec merged today; no gateway relays it yet) | Event subscriptions governed + audited at one on-box edge; no SaaS webhook broker in the delivery path | Filed [#2368](https://github.com/naveenreddyalka/daari/issues/2368) |
| 446 | Prove + fence long tool-name (>64 chars) governance — immune to litellm `tool_policy` fail-open (#47434/#52717, fixed 1.108.12 LTS) | 3 | 1 | LiteLLM (after its LTS patch) | Allowlist matching never truncates — argue it with hermetic tests across chat, Messages, MCP | Filed [#2369](https://github.com/naveenreddyalka/daari/issues/2369) |
| 447 | Speech-model discovery: `modality` filter + voice metadata on `/v1/models` | 3 | 2 | OpenRouter `/audio/speech/models` (11-19) | Local voice catalog discoverable on-box; agents stop hard-coding voice model ids | Filed [#2370](https://github.com/naveenreddyalka/daari/issues/2370) |
| 448 | Integration fence for the 11-18/11-19 overnight rpd/tpd + abort-stream wave | 2 | 2 | — (testability) | Hermetic proof: daily-exhaust walk continues, abort fails visibly end-to-end | Filed [#2371](https://github.com/naveenreddyalka/daari/issues/2371) |
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
| 414–423 | Team BYOK modality doors + credential attribution + reconcile + binding Prom + auto_caching/residency doctor+Prom + LTS 1.108.10 + fences | 2–4 | 1–3 | LiteLLM / Portkey / Kong | Tenant credential + cache dials + FinOps on one box | Filed [#2313](https://github.com/naveenreddyalka/daari/issues/2313)–[#2325](https://github.com/naveenreddyalka/daari/issues/2325) |
| 409–413 | Midstream tool-call safety + truncation Prom/Grafana; 409/411 Shipped | 2–5 | 1–2 | LiteLLM 1.111-dev | Local loops must not double-fire tools across a hop | Open [#2304](https://github.com/naveenreddyalka/daari/issues/2304)/[#2306](https://github.com/naveenreddyalka/daari/issues/2306)/[#2307](https://github.com/naveenreddyalka/daari/issues/2307); Shipped #2309/#2310 |
| 405 | Time-bounded catalog rates: `effective_to` promo windows + baseline fallback (Sol $4/$20 → $5/$30 on 11-21; Gemini 12-01 step-up class) | 4 | 2 | Kong 2.3.0 dynamic-pricing `effective_to`/`baseline_price` | Honest ledger through published price changes with no redeploy and no SaaS price feed | Filed [#2297](https://github.com/naveenreddyalka/daari/issues/2297) |
| 406 | Preserve every reasoning item + upstream output order on the frontier Responses path | 4 | 3 | LiteLLM 1.108.9 LTS (#51356 backport) | Byte-faithful item order on one box fronting local + frontier; encrypted replay keeps positional binding | Filed [#2298](https://github.com/naveenreddyalka/daari/issues/2298) |
| 407 | Surface local-tier thinking: capture Ollama `message.thinking` / OpenAI-compat `reasoning_content`, emit on chat + Responses + Messages | 4 | 3 | llama.cpp / vLLM emit it; LiteLLM relays it (1.108.9 #51748) | Local reasoning models are the pitch — daari pays the thinking tokens and must stop discarding the text | Filed [#2299](https://github.com/naveenreddyalka/daari/issues/2299) |
| 408 | Integration fence for the 11-14/11-15 overnight wave | 2 | 2 | — (testability) | Hermetic proof: thinking strip, toolset gate, baggage PATCH, encrypted reasoning | Filed [#2300](https://github.com/naveenreddyalka/daari/issues/2300) |
| 385–404 | Extractions + refused-leg + OCR + reasoning + ZDR + deadlines + tool-fee/reservation ops; MCP cancel / abandoned-stream spend / session pins / llama.cpp v1.0 **Shipped** (#2398–#2401) | 2–4 | 1–3 | LiteLLM / OpenRouter / Kong / llama.cpp | Same-box agent + FinOps honesty | Open [#2269](https://github.com/naveenreddyalka/daari/issues/2269)–[#2291](https://github.com/naveenreddyalka/daari/issues/2291); Shipped #2265–#2268 |
| 380 | `previous_response_id` must not replay failed/cancelled turns | 4 | 2 | LiteLLM 1.108.7 LTS (#48647) | On-box store skips poison history; local+frontier share one chain contract | Shipped (#2382) |
| 381 | Honor or honestly declare `max_tool_calls` (Responses-only fields) | 3 | 2 | LiteLLM 1.108.7 (#48655 drop_params / 400) | Enforce or `dropped_params` on-box — never silent, never smuggle to Bedrock | Shipped (#2383) |
| 382 | Claude Managed Agents self-hosted → daari Anthropic facade recipe | 4 | 2 | Anthropic CMA (hosted default); any Claude-shaped gateway | Local L0–L5 absorb CMA repeats at $0 before frontier | Filed [#2257](https://github.com/naveenreddyalka/daari/issues/2257) |
| 383 | compare-litellm: LTS floor → 1.108.7; Responses bridge + failed-turn positioning | 3 | 1 | LiteLLM release notes | Honest floor + diskcache differentiator next to tonight's LTS | Filed [#2258](https://github.com/naveenreddyalka/daari/issues/2258) |
| 384 | Integration fence for the 11-12 evening 1.108.7 / CMA wave | 2 | 2 | — (testability) | Hermetic proof: failed-chain, max_tool_calls honesty, cma-server metadata | Filed [#2259](https://github.com/naveenreddyalka/daari/issues/2259) |
| 375 | Bill frontier image generations/edits from upstream `usage`; gpt-image-2.6 catalog rates | 4 | 2 | OpenAI token-billed images; LiteLLM 1.108.6 Gemini image-edit billing | Image spend lands in the same-box ledger/budgets that meter chat | Shipped (#2373) |
| 376 | Bill the frontier ASR leg honestly (duration/token rates); local stays $0 | 3 | 2 | OpenAI per-minute/token ASR billing | The fallback that costs money is the leg the ledger must meter | Shipped (#2380) |
| 377 | Honor `tool_choice: allowed_tools` (nested + flat) across Anthropic + local backends | 3 | 2 | LiteLLM 1.108.6 LTS (#49043/#50467) | One tool-governance contract at the edge for every executor | Shipped (#2381) |
| 378 | Prove + fence client credential-field hygiene (immune to the litellm#51254 class); floors 1.109.1/1.108.6 | 3 | 1 | LiteLLM (after its emergency patch) | Allowlist payloads never needed the patch — argue it with a test | Shipped (#2358) |
| 379 | Integration fence for the 11-11/11-12 overnight wave | 2 | 2 | — (testability) | Hermetic proof: MCP egress fidelity, cost split, forensics, patterns | Filed [#2253](https://github.com/naveenreddyalka/daari/issues/2253) |
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Shipped (#2345) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Shipped (#2352) |
| 372–373 | Per-model daily `rpd`/`tpd` failover; abort / missing `finish_reason` stream honesty | 3–4 | 2 | LiteLLM 1.109.0 | Daily-quota walk + truncation honesty on-box | Shipped (#2365, #2366) |
| 374 | Integration fence for the 11-11 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: coding compose, Carbon rates, daily skip, abort | Filed [#2242](https://github.com/naveenreddyalka/daari/issues/2242) |
| 365–368 | Honest `stop_reason`; tool_call-arg guardrails; L0 keeps/excludes `tool_calls`; 1.109.0 compare floor | 3–4 | 1–2 | LiteLLM 1.109.0 fixes | Truncation + secret honesty on one box | Shipped (#2329, #2342–#2344) |
| 369 | Integration fence for the 11-10/11-11 overnight wave | 2 | 2 | — (testability) | Hermetic proof: cost-aware selection prefers $0 local; SLO panel pinned | Filed [#2236](https://github.com/naveenreddyalka/daari/issues/2236) |
| 360–361 | Residency CA/SG/KR/GB/AE 1.10×; Anthropic auto_caching | 2–3 | 1–2 | OpenAI / Portkey 2.33.0 | Governance + cache dials on the same-box console | Shipped (#2319, #2320) |
| 362–363 | any-5xx failover; Fable/Mythos 5.2 advisor gate | 2–3 | 1–2 | Kong 2.3.0 / Anthropic | Failover + advisor honesty | Shipped (#2327, #2328) |
| 364 | Integration fence for the 11-10 evening residency/caching/failover wave | 2 | 2 | — (testability) | Hermetic proof of that wave's dials | Filed [#2224](https://github.com/naveenreddyalka/daari/issues/2224) |
| 356 | Responses `truncation` auto/disabled | 3 | 2 | LiteLLM 1.108.4 | On-box compact vs honest 400 against serving window | Shipped (#2302) |
| 357–358 | Team BYOK; Ripple recipe | 2–4 | 1–3 | Ollama 0.40.16 | Tenant + local catalog on-box | Shipped (#2311, #2312) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
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
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **LiteLLM floor → 1.110.2 / 1.108.14
LTS** (fold into open 437); **1.112.0-dev.1** remainder (control
plane, capacity borrow, Skills Hub preserve — hold GA; fold compare
into 442/437, do not file a fifth); Anthropic API version
**2026-10-21** (noted in 454); Anthropic linked billing on Batches /
CMA ("not covered yet" — 465 is Messages+chat only); Genie 4
Interactions / full Live WS (row 8; 461 is catalog-only); **SEP-3415
stream/webhook** (445 is list+poll); OpenRouter TTS
`input_references` (447 first); Kong OSS 3.9.5 + AI Gateway 2.3.2
nginx CVEs (docs note); Opus 4.8 fast removal **11-30** (shield
#2053); Inkling 2 Mini (Apple-only — recipe once PC support lands);
vLLM 0.34 remainder; Portkey MCP policies; FIPS; A2A 1.1 RC; MCP
SEP-3398; SCIM + multi-issuer SSO. **Sol promo → $5/$30 on
2026-11-30** (460 corrects the date; 405 implements effective_to).

Verified fine this run — don't re-audit: `/v1/decisions` already
parses `input_json` content parts (decisions.py L444/457 — litellm
#52807 N/A); `anthropic-beta` passthrough in-tree (#455 — 465 needs
only the body field + ledger); Responses chains replay the flattened
`_conversation`, never raw provider blocks (464 is the fence, not a
fix); facade forwards `think` / `tool_search` / `format` / `logprobs`
(#1011/#1066 — `tools` is the one missing field, 467); Ollama
thinking-disable mapping + schema-keyword keeping are upstream-side
(daari forwards both verbatim on the local tier).

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy truth everywhere money and data move** —
   **Anthropic linked billing bill-to (465)**; **Flex wind-down
   price fence (466)**; **Sol promo date honesty → 11-30 (460)** +
   effective_to (405); Anthropic forwarded-cred catalog billing
   (463); GPT-Live catalog (461); GPT-6.2 chat-leg cache (455);
   introspect scope (456); Ultrafast (450); background windows
   (452); GPT-6.2 catalog (444); Hydrogen (439); BYOK doors
   (414–416); zero_retention (435); refused-leg / OCR (391/396).
   ASR + abandoned-stream shipped.
2. **Honest terminal outcomes + frontier wire-shape hygiene** —
   Fable/Mythos param_compat (454); GPT-6.2 param_compat (449);
   store:false developer (451); server-tool replay fence (464);
   stream no-dup fence (457); truncated cache gate (424); frontier
   stream honesty (425); Responses `incomplete` (426); overload
   envelopes (436); long tool-name (446); finish_reason Prom (431).
3. **Nothing goes stale quietly** — exhausted-key discovery fence
   (462); performance alerts (440); `rate_limited_by` (441);
   deprecation exposure (434); 5xx/auto_caching doctor+Prom
   (429–430, 419–420); MCP re-mint (395); deadlines (400); ZDR
   (398). MCP cancel + session pins shipped (#2398, #2400).
4. **Agent-protocol + tool-loop fidelity** — **Ollama facade tools
   (467)**; **deferred tool schema (459)**; MCP Events (445);
   Responses order + reasoning (406); local thinking (407);
   Extractions (390); OpenRouter reasoning (397). CMA recipe,
   failed-chain, max_tool_calls, allowed_tools shipped.
5. **Local engine floor + discovery + honest compare** — speech
   discovery (447); Live catalog (461) ahead of full WS; 1.111/1.112
   watch (442 + fold); LiteLLM floor 1.110.2 / 1.108.14 (437); vLLM
   0.34 (427); watermark (433); HF keys (432); fences through 468;
   then 62–67. llama.cpp v1.0 guide shipped (#2401).

---

## Changelog

- **2026-11-21 (linked billing + facade tools + Flex wind-down)** —
  Mined Anthropic linked billing beta (`billing_policy`,
  `user-profiles-billing-2026-10-01`), the 11-21 OpenAI Flex
  wind-down amendment, LiteLLM 1.108.14 LTS (#50821, #52807), and
  Ollama 0.40.17 GA. Filed: server-tool replay fence (464); linked
  billing bill-to (465); Flex capability + price fence (466);
  **Ollama facade tool calling** (467 — `/api/chat` drops `tools`
  today); overnight fence (468). Verified fine: decisions
  `input_json` parsed; `anthropic-beta` forwards. Overnight
  #2265–#2268 Shipped (#2398–#2401). Floor promote 1.108.14 folded
  into watch/437.

- **2026-11-20 pm (Sol date + deferred tools + Live + BYOK price)** —
  Mined OpenAI pricing (Sol promo → **11-30**), GPT-Live-1.1 standby
  rates, OpenRouter Tool Search / Gemini Tool Retrieval
  `defer_loading`, LiteLLM 1.112.0-dev.1 (#52313, #51675). Filed:
  deferred tool schema (459); Sol end-date honesty (460); GPT-Live
  catalog (461); exhausted-key discovery fence (462); Anthropic
  forwarded-cred catalog billing (463). Afternoon CMA + LTS compare
  Shipped (#2390, #2391). Tool Retrieval / Live WS remain watch
  beyond 459/461.

- **2026-11-20 (litellm five-line patch night, audited)** — Mined
  1.110.2 / 1.109.3 / 1.108.13 LTS / 1.106.12 / 1.111.0-rc.3 plus the
  Anthropic 5.2 migration guide and API version 2026-10-21. Filed:
  Fable/Mythos 5.1+5.2 param_compat (454); GPT-6.2 chat-leg
  system→developer cache placement (455, adjacent to 451);
  `/introspect` scoping (456); no-duplicate stream prove+fence (457);
  overnight fence (458). Verified immune: header-free cache keys,
  no server-side SSO redirect, buffer-then-flush streams. Overnight
  376–377 + 380–381 Shipped (#2380–#2383). Floor promote folded into
  watch/437.

- **2026-11-19 (+pm)** — Condensed: GPT-6.2 day-0 cut (444–448:
  catalog, SEP-3415 Events, long-tool-name fence, TTS discovery,
  fence; stuck 11-18 pm PRD PR repaired in-run); pm wire-shape
  follow-through (449–453: 6.2 param_compat, Ultrafast, store:false
  developer placement, background windows, fence). 372–373 + image
  billing Shipped (#2365, #2366, #2373).

- **2026-11-18 (+pm)** — Condensed: 1.110.0 stable (Rust-only
  router, ledger-default) + 1.108.11 LTS mined → successor/
  zero_retention/overload/compare/fence (434–438); pm mined
  1.111.0-rc.1 → Hydrogen, alerts, `rate_limited_by`, RC watch,
  fence (439–443). Overnight 366–368 + 370 Shipped (#2342–#2345);
  afternoon #2352/#2358.

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
