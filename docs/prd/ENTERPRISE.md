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

## Where daari stands (verified in-tree, 2026-11-24)

**Loop velocity.** Overnight shipped Fable/Mythos 5.1+5.2 param_compat
(#2437 → #2384) and ZDR honesty for retention-required Fable/Mythos
(#2438 → #2284). Sunday's OCR pages-billing + OpenRouter reasoning object
(#2432/#2433) remain on main. Open bands 474–485 still in flight.

**Outward.** Monday delta: **Anthropic 11-23** — Enterprise Frontier
Safeguards (EFS) beta (ZDR with customer-owned Sealed Safety Data;
`external_storage.failed` / `external_storage.recovered` webhooks) and
**Opus 4.5 deprecation** (retire **2027-01-22** → Opus 5.5).
**LiteLLM 1.108.16 LTS** (11-23 ~22:12 UTC) — MCP DCR opt-in backport,
anthropic-version 2026-10-21 sampling drop, Gradium TTS, Gemini
`video_url`, decisions/`litellm_proxy`. OpenRouter flat past 11-23 Tool
Search schemas + `allow_provisional_providers` on guardrails (fold
schemas into 459; provisional → watch). Ollama 0.40.17; vLLM 0.34.0;
Kong 3.9.5; Portkey backend 1.31.0 / enterprise 2.33.1; 1.112.0-dev.2
and 1.110.2/1.111-rc unchanged.

**Inward theme: ZDR + lifecycle honesty after the overnight refuse.**
`models.retention_authorized` ships without naming EFS (486); Opus 4.5
missing from `_DEFAULT_MODEL_LIFECYCLE` (487); retention refuses have no
Prom/stats (489); LTS compare still cites 1.108.15 (488); fence the wave
(490). `/v1/responses` `reasoning.exclude` (484) still open.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 487 | Pin Claude Opus 4.5 deprecation lifecycle — retires 2027-01-22, successor Opus 5.5; `_DEFAULT_MODEL_LIFECYCLE` is OpenAI-only today | 4 | 1 | Anthropic platform notes / LiteLLM catalog | On-box `/v1/models` + doctor show the cutover; local tiers keep cheap loops | Filed [#2439](https://github.com/naveenreddyalka/daari/issues/2439) |
| 486 | EFS honesty for `models.retention_authorized` — doctor + config docs name Enterprise Frontier Safeguards / customer-owned Sealed Safety Data (Anthropic 11-23) | 4 | 2 | Anthropic EFS console | Override is an honest EFS exception, not a silent ZDR lie | Filed [#2440](https://github.com/naveenreddyalka/daari/issues/2440) |
| 489 | Prometheus + stats for `zdr_retention_required` refusals — overnight refuse is ops-blind | 3 | 1 | LiteLLM spend/guardrail metrics | Graph impossible ZDR+Fable asks before frontier spend | Filed [#2441](https://github.com/naveenreddyalka/daari/issues/2441) |
| 488 | Promote LiteLLM LTS compare floor to **1.108.16** (MCP DCR opt-in, anthropic-version sampling, Gradium/Gnani/Perplexity, video_url) | 2 | 1 | LiteLLM LTS notes | Honest procurement floor; daari non-goals stay clear | Filed [#2442](https://github.com/naveenreddyalka/daari/issues/2442) |
| 490 | Integration fence for the 11-23/11-24 Fable param_compat + ZDR retention + Opus/EFS follow-through wave | 2 | 2 | — (testability) | Hermetic proof of overnight + today's pins | Filed [#2443](https://github.com/naveenreddyalka/daari/issues/2443) |
| 484 | Honor `reasoning.exclude` on `/v1/responses` — door parses OpenRouter reasoning but `_output_items_from_result` emits reasoning anyway | 3 | 1 | OpenRouter /responses | Same strip as chat (#2433); billing truth stays | Filed [#2434](https://github.com/naveenreddyalka/daari/issues/2434) |
| 485 | Integration fence for the 11-22/11-23 overnight OCR pages-billing + reasoning-object wave | 2 | 2 | — (testability) | Hermetic proof of that ship | Filed [#2435](https://github.com/naveenreddyalka/daari/issues/2435) |
| 479 | Ship Gemini 4 Neon catalog rates + capabilities + `xhigh` thinking ($3/$15, cache $0.15) | 4 | 2 | Google AI Studio / LiteLLM | Day-0 ledger match; local tiers absorb cheap loops | Filed [#2426](https://github.com/naveenreddyalka/daari/issues/2426) |
| 480 | Operator dial to omit `X-Daari-*` response headers (litellm `include_litellm_headers`) | 3 | 2 | LiteLLM 1.112.0-dev.2 | Clean OpenAI-shaped surface; ledger/Prom keep telemetry | Filed [#2427](https://github.com/naveenreddyalka/daari/issues/2427) |
| 481 | Bill Priority rates + cached image tokens on image/multimodal legs | 3 | 2 | LiteLLM 1.112.0-dev.2 | Priority vision matches invoice; local image $0 | Filed [#2428](https://github.com/naveenreddyalka/daari/issues/2428) |
| 482 | Honor OpenRouter `provider.zdr` / `data_collection` on image (and video) doors | 3 | 2 | OpenRouter native | One edge enforces data-policy across modalities | Filed [#2429](https://github.com/naveenreddyalka/daari/issues/2429) |
| 483 | Integration fence for the 11-22 afternoon MCP secret / Neon / omit-headers / image-priority wave | 2 | 2 | — (testability) | Hermetic proof | Filed [#2430](https://github.com/naveenreddyalka/daari/issues/2430) |
| 474 | Operator data-policy floor for marketplace legs — force `zdr`/`data_collection` on OpenRouter | 4 | 2 | OpenRouter (reactive) | One on-box floor; client prefs tighten only | Filed [#2418](https://github.com/naveenreddyalka/daari/issues/2418) |
| 475–478 | Cache-Control; refuse `previous_response_id` on chat/Messages; TTS duration billing; overnight fence | 2–3 | 1–2 | LiteLLM 1.112.0-dev.2 | RFC + loud refuse + duration math | Filed [#2419](https://github.com/naveenreddyalka/daari/issues/2419)–[#2422](https://github.com/naveenreddyalka/daari/issues/2422) |
| 469–473 | Linked-billing refuses; TTS `input_references`; Extractions BYOK; fence | 2–4 | 1–2 | Anthropic / OpenRouter | Bill-to + voice + tenant Extractions | Filed [#2409](https://github.com/naveenreddyalka/daari/issues/2409)–[#2413](https://github.com/naveenreddyalka/daari/issues/2413) |
| 464–468 | Server-tool replay fence; bill-to forward; Flex wind-down; Ollama facade tools; fence | 2–4 | 1–2 | LiteLLM / Anthropic / Ollama | Wire-shape + facade tool loop | Filed [#2402](https://github.com/naveenreddyalka/daari/issues/2402)–[#2406](https://github.com/naveenreddyalka/daari/issues/2406) |
| 459–463 | Deferred tools; Sol end **11-30**; Live catalog; exhausted-key discovery; BYOK Anthropic price fence | 2–4 | 1–3 | OpenRouter / OpenAI / LiteLLM | Agent + FinOps honesty | Filed [#2392](https://github.com/naveenreddyalka/daari/issues/2392)–[#2396](https://github.com/naveenreddyalka/daari/issues/2396) |
| 454–458 | Fable/Mythos param_compat; 6.2 chat-leg cache; introspect scope; stream no-dup; fence | 2–5 | 1–2 | LiteLLM / Anthropic | Flagship wire-shape hygiene | **454 Shipped** (#2437); open [#2385](https://github.com/naveenreddyalka/daari/issues/2385)–[#2388](https://github.com/naveenreddyalka/daari/issues/2388) |
| 449 | GPT-6.2 param_compat | 5 | 1 | OpenAI / LiteLLM | Pure-Python edge table | Shipped (#2417) |
| 450–453 | Ultrafast; store:false developer; background windows; fence | 2–4 | 2 | OpenAI / LiteLLM | 6.2 follow-through | Filed [#2375](https://github.com/naveenreddyalka/daari/issues/2375)–[#2378](https://github.com/naveenreddyalka/daari/issues/2378) |
| 444–448 | GPT-6.2 catalog; SEP-3415 Events; long-tool-name fence; speech discovery; fence | 2–4 | 1–3 | OpenAI / MCP | Day-0 catalog + Events | Filed [#2367](https://github.com/naveenreddyalka/daari/issues/2367)–[#2371](https://github.com/naveenreddyalka/daari/issues/2371) |
| 434–443 | successor_model; zero_retention; overload; Hydrogen; alerts; `rate_limited_by`; 1.111 watch; fences | 2–4 | 1–3 | LiteLLM / Google | Tenancy + ops dials | Filed [#2346](https://github.com/naveenreddyalka/daari/issues/2346)–[#2363](https://github.com/naveenreddyalka/daari/issues/2363) |
| 424–433 | Truncated-cache; stream honesty; Responses `incomplete`; vLLM 0.34; 5xx/finish_reason Prom; HF; watermark | 2–4 | 1–3 | OpenAI / Kong / LiteLLM | Terminal + ops honesty | Filed [#2330](https://github.com/naveenreddyalka/daari/issues/2330)–[#2340](https://github.com/naveenreddyalka/daari/issues/2340) |
| 414–423 | Team BYOK modality + credential attribution + reconcile + binding Prom + auto_caching/residency + LTS + fences | 2–4 | 1–3 | LiteLLM / Portkey / Kong | Tenant credential + cache dials | Filed [#2313](https://github.com/naveenreddyalka/daari/issues/2313)–[#2325](https://github.com/naveenreddyalka/daari/issues/2325) |
| 409–413 | Midstream tool-call safety + truncation Prom/Grafana | 2–5 | 1–2 | LiteLLM 1.111-dev | Local loops must not double-fire | Open [#2304](https://github.com/naveenreddyalka/daari/issues/2304)/[#2306](https://github.com/naveenreddyalka/daari/issues/2306)/[#2307](https://github.com/naveenreddyalka/daari/issues/2307) |
| 405–408 | effective_to promos; Responses order; local thinking; fence | 2–4 | 2–3 | Kong / LiteLLM | Honest ledger + reasoning | Filed [#2297](https://github.com/naveenreddyalka/daari/issues/2297)–[#2300](https://github.com/naveenreddyalka/daari/issues/2300) |
| 385–404 | Extractions + OCR + reasoning + ZDR + deadlines + tool-fee ops; MCP cancel / pins / llama.cpp / refused-leg / cost panels / OCR pages / reasoning object / **ZDR retention** | 2–4 | 1–3 | LiteLLM / OpenRouter / Kong / Anthropic | Same-box agent + FinOps | Open [#2269](https://github.com/naveenreddyalka/daari/issues/2269)–[#2291](https://github.com/naveenreddyalka/daari/issues/2291); Shipped #2265–#2268, #2272–#2273, #2398–#2401, #2415–#2416, #2432–#2433, **#2438** |
| 375–384 | Image/ASR billing; allowed_tools; failed-chain; max_tool_calls; CMA; LTS — most Shipped | 2–4 | 1–2 | LiteLLM / Anthropic | Wire + FinOps | Open [#2253](https://github.com/naveenreddyalka/daari/issues/2253)/[#2257](https://github.com/naveenreddyalka/daari/issues/2257)–[#2259](https://github.com/naveenreddyalka/daari/issues/2259) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger meters; finish the console | Open (agent:working) |
| 19–28 | compact_to_fit + MCP grant fail-closed wave | 2–4 | 1–2 | LiteLLM | Shipped | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **LiteLLM floor → 1.110.2 / 1.108.16
LTS** (488 is the LTS pin; fold GA into open 437/2349); **1.112.0-dev.2**
remainder (**Lens**, FIPS 140-3 image, custom spend windows,
budget-reservation sizing, app-budget presets — hold GA); incomplete
synthetic-stream event (fold into 426); semantic-router 1.2.0
matched-utterances; OpenRouter canary ZDR verification (474 floor; 482
image wire); OpenRouter **`allow_provisional_providers`** on guardrails
(11-23 — fold when OR guardrail authoring lands); Anthropic linked-billing
error codes (465/469/470); Anthropic CMEK + **EFS webhook relay**
(watch; 486 is docs/doctor only); API version **2026-10-21**; Genie 4
Interactions / full Live WS (row 8; 461 catalog-only); SEP-3415
stream/webhook (445 is list+poll); OpenRouter Messages Tool Search wire
schemas (11-23) — fold into 459, never file separately; MCP next
**2027-03-30**; Kong OSS 3.9.5 + AI Gateway 2.3.2; Opus 4.8 fast removal
**11-30**; Inkling 2 Mini (Apple-only); vLLM 0.34 remainder; Portkey MCP
policies; A2A 1.1 RC; SCIM + multi-issuer SSO; Microsoft Web IQ
`/v1/search`. **Sol promo → $5/$30 on 2026-11-30** (460 + 405).

Verified fine this run — don't re-audit: overnight ZDR retention refuse +
doctor tip on zdr slots (#2438); Fable/Mythos param_compat unit coverage
(#2437); L0 cache × chat `reasoning.exclude` interplay; per-request
`provider.zdr` fails closed (474 operator floor; 482 image wire; EFS is
the Anthropic-authorized exception path for 486).

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy + data-policy + lifecycle truth** — **Opus 4.5
   lifecycle (487)**; **EFS honesty for retention_authorized (486)**;
   Neon catalog (479); Priority/cached-image (481); image/video provider
   prefs (482); marketplace floor (474); TTS duration (477); linked-billing
   refuses (469–470); Extractions BYOK (472); Flex wind-down (466); Sol →
   11-30 (460) + effective_to (405); Live catalog (461); zero_retention
   (435). ZDR retention refuse shipped.
2. **Honest terminal outcomes + frontier wire-shape** —
   reasoning.exclude on /v1/responses (484); previous_response_id refuse
   (476); store:false developer (451); Responses `incomplete` (426);
   truncated cache gate (424); frontier stream honesty (425); overload
   envelopes (436). GPT-6.2 + Fable/Mythos param_compat + chat reasoning
   object shipped.
3. **Nothing goes stale quietly** — **zdr_retention Prom (489)**;
   **LTS 1.108.16 compare (488)**; omit X-Daari headers (480);
   Cache-Control (475); exhausted-key discovery (462); performance alerts
   (440); `rate_limited_by` (441); deprecation exposure (434); 5xx/
   auto_caching doctor+Prom (429–430, 419–420).
4. **Agent-protocol + tool-loop + voice fidelity** — TTS
   `input_references` (471); Ollama facade tools (467); deferred tools
   (459); MCP Events (445); Responses order + reasoning (406); local
   thinking (407).
5. **Local engine floor + discovery + honest compare + fences** — speech
   discovery (447); Live catalog (461); 1.111/1.112 watch (442); vLLM
   0.34 (427); fences through **490**; then 62–67.

---

## Changelog

- **2026-11-24 (Anthropic EFS + Opus 4.5 + LiteLLM 1.108.16)** — Outward:
  Anthropic EFS beta + Opus 4.5 retire 2027-01-22; LiteLLM LTS 1.108.16;
  OpenRouter provisional-providers on guardrails (watch). Inward: audited
  overnight #2437/#2438; retention_authorized undocumented vs EFS; Opus
  4.5 absent from lifecycle defaults; retention refuses uncounted; LTS
  compare stale at 1.108.15. Filed: Opus 4.5 lifecycle (487); EFS
  doctor/docs (486); zdr_retention Prom (489); LTS 1.108.16 compare
  (488); overnight fence (490). 454 + #2284 Shipped.

- **2026-11-23 (Sunday-flat; reasoning follow-through)** — OpenRouter
  Tool Search schemas (fold 459); /v1/responses emits reasoning despite
  `exclude`. Filed 484–485. Unparked sibling PR #2431 pin suite.

- **2026-11-22 pm → 11-14** — Condensed: Neon / omit headers / Priority
  image / image ZDR (479–483); OR data-policy + Cache-Control + TTS
  duration (474–478); linked billing + Flex + facade tools (464–473);
  Fable/6.2/deferred/Live (454–463); GPT-6.2 day-0 (444–453); 1.110/
  Hydrogen/alerts (434–443); truncation + vLLM (424–433); BYOK +
  midstream + thinking (405–423).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg /
  llama.cpp v1.0; CMA + 1.108.x; coding-router / Gemini 4 / Kong 2.3.0
  through Apache 2.0 and this PRD's creation. #2141 needs human close.
