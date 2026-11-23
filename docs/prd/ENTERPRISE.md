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

## Where daari stands (verified in-tree, 2026-11-23)

**Loop velocity.** Overnight shipped OCR pages-processed billing
(#2432 → issue #2282) and the OpenRouter `reasoning` object on
chat/completions (#2433 → issue #2283) — both from the 385–404 band.
The 11-22 waves 474–483 and older bands remain open.

**Outward.** Sunday-flat: LiteLLM unchanged past 1.112.0-dev.2 /
1.108.15 LTS; OpenAI flat past GPT-Live-1.1 (11-19); Anthropic flat
past 11-17; Gemini flat past Tool Retrieval (11-19); Ollama 0.40.17;
vLLM 0.34.0; Kong 2.3.2; Portkey backend 1.31.0 (11-05); MCP blog
flat. Only delta: **OpenRouter API changelog 11-23** adds
`MessagesToolSearchTool*` schemas on `POST /messages` — Tool Search
reference + result blocks on the Anthropic wire shape (folds into
open 459 / #2392, which already targets tool_search on both doors) —
plus an `/images` example touch; 11-21 added `pareto-inference` to
`ProviderOptions` and new BYOK provider slugs (pass-through for daari).

**Inward theme: reasoning follow-through.** `/v1/responses` parses the
OpenRouter `reasoning` object (the `from_responses_body` → 
`from_openai_body` delegation carries `exclude`/`max_tokens`/`enabled`)
but `_output_items_from_result` emits reasoning items unconditionally —
the one door that accepts `exclude` and returns reasoning anyway (484);
the overnight wave is unfenced (485).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 484 | Honor `reasoning.exclude` on `/v1/responses` — door parses the OpenRouter reasoning object but `_output_items_from_result` (responses.py ~L356) + stream `output_item.added` emit reasoning items regardless; usage must still bill | 3 | 1 | OpenRouter /responses (native exclude) | Same strip machinery shipped for chat in #2433; wiring one builder makes exclude honest across every door while the on-box ledger keeps billing truth | Filed [#2434](https://github.com/naveenreddyalka/daari/issues/2434) |
| 485 | Integration fence for the 11-22/11-23 overnight OCR pages-billing + reasoning-object wave | 2 | 2 | — (testability) | Hermetic proof: pages × catalog rate in ledger, effort parity, exclude strip with usage preserved, dropped context/mode | Filed [#2435](https://github.com/naveenreddyalka/daari/issues/2435) |
| 479 | Ship Gemini 4 Neon catalog rates + capabilities + `xhigh` thinking ($3/$15, cache $0.15; GA 11-18) | 4 | 2 | Google AI Studio / LiteLLM day-0 cost maps | On-box ledger matches Neon invoice on day 0; local tiers still absorb cheap loops | Filed [#2426](https://github.com/naveenreddyalka/daari/issues/2426) |
| 480 | Operator dial to omit `X-Daari-*` response headers — always-on cost/tier/warning headers today (litellm `include_litellm_headers` #52949) | 3 | 2 | LiteLLM 1.112.0-dev.2 | Same-box telemetry stays in ledger/Prom; clients get a clean OpenAI-shaped surface | Filed [#2427](https://github.com/naveenreddyalka/daari/issues/2427) |
| 481 | Bill Priority rates + cached image tokens on image/multimodal legs — `price_image_request` skips `service_tier_factor` and cached-image rate (litellm #52972) | 3 | 2 | LiteLLM 1.112.0-dev.2 | Priority vision turns must match invoice; local image paths stay $0 | Filed [#2428](https://github.com/naveenreddyalka/daari/issues/2428) |
| 482 | Honor OpenRouter `provider.zdr` / `data_collection` on image (and video) modality doors — `ImagesGenerationsRequest` has no `provider` field (OR changelog 11-13 + Dragos 11-22) | 3 | 2 | OpenRouter native image/video prefs | One edge enforces data-policy across every modality that leaves the box | Filed [#2429](https://github.com/naveenreddyalka/daari/issues/2429) |
| 483 | Integration fence for the 11-22 afternoon MCP secret re-resolve + Neon/omit-headers/image-priority wave | 2 | 2 | — (testability) | Hermetic proof: secret near-use, Neon pin, header omit, Priority image, image zdr | Filed [#2430](https://github.com/naveenreddyalka/daari/issues/2430) |
| 474 | Operator data-policy floor for marketplace legs — client-only `provider` prefs; nothing forces `zdr`/`data_collection: deny`/`only` onto every OpenRouter leg (Dragos/OR 11-22) | 4 | 2 | OpenRouter (reactive off-boarding) | One on-box floor; client prefs tighten, never weaken | Filed [#2418](https://github.com/naveenreddyalka/daari/issues/2418) |
| 475 | Honor standard `Cache-Control` — `no-cache` skips reads, `no-store` skips reads+puts; only `X-Daari-No-Cache` today (litellm #52840) | 3 | 2 | LiteLLM 1.112.0-dev.2 | RFC 9111 shapes; $0 cache earns trust | Filed [#2419](https://github.com/naveenreddyalka/daari/issues/2419) |
| 476 | Refuse `previous_response_id` on chat + Messages — `extra="ignore"` silent drop (litellm #53038) | 3 | 1 | LiteLLM 1.112.0-dev.2 | Refuse loudly; point at /v1/responses | Filed [#2420](https://github.com/naveenreddyalka/daari/issues/2420) |
| 477 | Bill frontier TTS from returned audio duration — `audio_bytes // 4` fiction (litellm #53150) | 3 | 2 | LiteLLM 1.112.0-dev.2 | Duration math local; local TTS $0 | Filed [#2421](https://github.com/naveenreddyalka/daari/issues/2421) |
| 478 | Integration fence for the 11-21/11-22 overnight refused-leg billing, cost panels, GPT-6.2 param_compat wave | 2 | 2 | — (testability) | Hermetic proof of that wave | Filed [#2422](https://github.com/naveenreddyalka/daari/issues/2422) |
| 469–473 | Linked-billing refuses; TTS `input_references`; Extractions BYOK; fence | 2–4 | 1–2 | Anthropic / OpenRouter | Bill-to + voice + tenant Extractions on one box | Filed [#2409](https://github.com/naveenreddyalka/daari/issues/2409)–[#2413](https://github.com/naveenreddyalka/daari/issues/2413) |
| 464–468 | Server-tool replay fence; bill-to forward; Flex wind-down; Ollama facade tools; fence | 2–4 | 1–2 | LiteLLM / Anthropic / Ollama 0.40.17 | Wire-shape + facade tool loop | Filed [#2402](https://github.com/naveenreddyalka/daari/issues/2402)–[#2406](https://github.com/naveenreddyalka/daari/issues/2406) |
| 459–463 | Deferred tools; Sol end **11-30**; Live catalog; exhausted-key discovery; BYOK Anthropic price fence | 2–4 | 1–3 | OpenRouter / OpenAI / LiteLLM | Agent + FinOps honesty | Filed [#2392](https://github.com/naveenreddyalka/daari/issues/2392)–[#2396](https://github.com/naveenreddyalka/daari/issues/2396) |
| 454–458 | Fable/Mythos param_compat; 6.2 chat-leg cache; introspect scope; stream no-dup; fence | 2–5 | 1–2 | LiteLLM / Anthropic | Flagship wire-shape hygiene | Filed [#2384](https://github.com/naveenreddyalka/daari/issues/2384)–[#2388](https://github.com/naveenreddyalka/daari/issues/2388) |
| 449 | GPT-6.2 param_compat — strip sampling, floor effort, `tools_transport=responses` | 5 | 1 | OpenAI / LiteLLM | Pure-Python edge table | Shipped (#2417) |
| 450–453 | Ultrafast; store:false developer; background windows; fence | 2–4 | 2 | OpenAI / LiteLLM | 6.2 follow-through | Filed [#2375](https://github.com/naveenreddyalka/daari/issues/2375)–[#2378](https://github.com/naveenreddyalka/daari/issues/2378) |
| 444–448 | GPT-6.2 catalog; SEP-3415 Events; long-tool-name fence; speech discovery; fence | 2–4 | 1–3 | OpenAI / MCP | Day-0 catalog + Events | Filed [#2367](https://github.com/naveenreddyalka/daari/issues/2367)–[#2371](https://github.com/naveenreddyalka/daari/issues/2371) |
| 439–443 | Hydrogen; alerts; `rate_limited_by`; 1.111 RC watch; fence | 2–4 | 1–3 | Google / LiteLLM | Gemini + ops dials | Filed [#2359](https://github.com/naveenreddyalka/daari/issues/2359)–[#2363](https://github.com/naveenreddyalka/daari/issues/2363) |
| 434–438 | successor_model; zero_retention; overload envelopes; 1.110 compare; fence | 2–4 | 1–3 | LiteLLM 1.110.0 | Tenancy + typed errors | Filed [#2346](https://github.com/naveenreddyalka/daari/issues/2346)–[#2350](https://github.com/naveenreddyalka/daari/issues/2350) |
| 429–433 | 5xx doctor+Prom; finish_reason Prom; HF keys; watermark; vLLM 0.34 | 2–3 | 1–2 | Kong / LiteLLM / Anthropic | Ops honesty | Filed [#2336](https://github.com/naveenreddyalka/daari/issues/2336)–[#2340](https://github.com/naveenreddyalka/daari/issues/2340); [#2333](https://github.com/naveenreddyalka/daari/issues/2333) |
| 424–428 | Truncated-cache gate; frontier stream honesty; Responses `incomplete`; vLLM notes; fence | 2–4 | 1–3 | OpenAI / LiteLLM | Terminal-outcome truth | Filed [#2330](https://github.com/naveenreddyalka/daari/issues/2330)–[#2334](https://github.com/naveenreddyalka/daari/issues/2334) |
| 414–423 | Team BYOK modality doors + credential attribution + reconcile + binding Prom + auto_caching/residency doctor+Prom + LTS + fences | 2–4 | 1–3 | LiteLLM / Portkey / Kong | Tenant credential + cache dials | Filed [#2313](https://github.com/naveenreddyalka/daari/issues/2313)–[#2325](https://github.com/naveenreddyalka/daari/issues/2325) |
| 409–413 | Midstream tool-call safety + truncation Prom/Grafana; 409/411 Shipped | 2–5 | 1–2 | LiteLLM 1.111-dev | Local loops must not double-fire | Open [#2304](https://github.com/naveenreddyalka/daari/issues/2304)/[#2306](https://github.com/naveenreddyalka/daari/issues/2306)/[#2307](https://github.com/naveenreddyalka/daari/issues/2307) |
| 405–408 | effective_to promos; Responses order; local thinking; fence | 2–4 | 2–3 | Kong / LiteLLM | Honest ledger + reasoning | Filed [#2297](https://github.com/naveenreddyalka/daari/issues/2297)–[#2300](https://github.com/naveenreddyalka/daari/issues/2300) |
| 385–404 | Extractions + OCR + reasoning + ZDR + deadlines + tool-fee ops; MCP cancel / abandoned-stream / session pins / llama.cpp v1.0 / refused-leg / cost panels / OCR pages billing / reasoning object **Shipped** | 2–4 | 1–3 | LiteLLM / OpenRouter / Kong | Same-box agent + FinOps | Open [#2269](https://github.com/naveenreddyalka/daari/issues/2269)–[#2291](https://github.com/naveenreddyalka/daari/issues/2291); Shipped #2265–#2268, #2272–#2273, #2398–#2401, #2415–#2416, #2432–#2433 |
| 375–384 | Image/ASR billing; allowed_tools; failed-chain; max_tool_calls; CMA; LTS compare — most Shipped | 2–4 | 1–2 | LiteLLM / Anthropic | Wire + FinOps | Open [#2253](https://github.com/naveenreddyalka/daari/issues/2253)/[#2257](https://github.com/naveenreddyalka/daari/issues/2257)–[#2259](https://github.com/naveenreddyalka/daari/issues/2259); Shipped #2373, #2380–#2383, #2390 |
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

Watch rows (do not file yet): **LiteLLM floor → 1.110.2 / 1.108.15
LTS** (fold into open 437); **1.112.0-dev.2** remainder (**Lens**,
FIPS 140-3 image, MCP DCR opt-in, custom spend windows, budget-reservation
sizing, app-budget presets/alerts — hold GA; fold compare into 442/437);
**incomplete synthetic-stream event** (fold into open 426 / #2332);
**semantic-router 1.2.0** matched-utterances vs L1 shadow diagnostics
(docs/compare when L1 UX lands); OpenRouter canary-style ZDR verification
(474 is the daari floor; 482 is modality wire); Anthropic linked-billing
error codes (fold into 465/469/470); Anthropic CMEK webhooks; API version
**2026-10-21**; linked billing on Batches/CMA still unsupported upstream;
Genie 4 Interactions / full Live WS (row 8; 461 catalog-only); SEP-3415
stream/webhook (445 is list+poll); **OpenRouter Messages Tool Search
wire schemas (11-23)** — fold into 459 / #2392, never file separately;
MCP next **2027-03-30**; Kong OSS
3.9.5 + AI Gateway 2.3.2 nginx CVEs (docs note); Opus 4.8 fast removal
**11-30**; Inkling 2 Mini (Apple-only); vLLM 0.34 remainder; Portkey MCP
policies; A2A 1.1 RC; SCIM + multi-issuer SSO; Microsoft Web IQ
`/v1/search`. **Sol promo → $5/$30 on 2026-11-30** (460 + 405).

Verified fine this run — don't re-audit: L0 cache stores the full
`InternalResponse` (reasoning survives hits; `exclude` strips at the
edge post-cache, so it correctly stays out of the cache key);
`reasoning.max_tokens` buckets into `reasoning_effort`, which is in
`honored_fields()` keying; chat door strips exclude on stream +
non-stream (#2433). Prior runs: budget windows UTC-only; id-keyed
owner-gated file store; `no_cache` guards reads+puts (475 adds
standard headers); per-request `provider.zdr` fails closed (474
operator floor; 482 image wire).

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy + data-policy truth everywhere money and data
   move** — **Neon catalog (479)**; **Priority/cached-image billing
   (481)**; **image/video provider prefs (482)**; marketplace floor
   (474); TTS duration (477); linked-billing refuses (469–470) on
   bill-to forward (465); Extractions BYOK (472); Flex wind-down
   (466); Sol → 11-30 (460) + effective_to (405); forwarded-cred
   billing (463); Live catalog (461); Hydrogen (439); zero_retention
   (435). Refused-leg billing + cost-USD panels shipped.
2. **Honest terminal outcomes + frontier wire-shape hygiene** —
   **reasoning.exclude on /v1/responses (484)**; previous_response_id
   refuse (476); Fable/Mythos param_compat (454); store:false
   developer (451); Responses `incomplete` incl. stream event (426);
   truncated cache gate (424); frontier stream honesty (425);
   overload envelopes (436). GPT-6.2 param_compat + chat reasoning
   object shipped.
3. **Nothing goes stale quietly** — **omit X-Daari headers dial
   (480)**; Cache-Control (475); exhausted-key discovery (462);
   performance alerts (440); `rate_limited_by` (441); deprecation
   exposure (434); 5xx/auto_caching doctor+Prom (429–430, 419–420).
4. **Agent-protocol + tool-loop + voice fidelity** — TTS
   `input_references` (471); Ollama facade tools (467); deferred
   tools (459); MCP Events (445); Responses order + reasoning
   (406); local thinking (407). CMA recipe, Extractions, MCP
   cancel, session pins shipped.
5. **Local engine floor + discovery + honest compare** — speech
   discovery (447); Live catalog (461); 1.111/1.112 watch incl.
   Lens (442 + fold); LiteLLM floor 1.110.2 / 1.108.15 (437); vLLM
   0.34 (427); fences through 485; then 62–67. llama.cpp v1.0 guide
   + MCP secret re-resolve + OCR pages billing shipped.

---

## Changelog

- **2026-11-23 (Sunday-flat; reasoning follow-through)** — Outward
  flat everywhere except OpenRouter's 11-23 API changelog:
  `MessagesToolSearchTool*` schemas on `POST /messages` (folded into
  459 / #2392) + `pareto-inference` provider (pass-through). Inward:
  audited overnight #2432/#2433; verified cache×exclude interplay
  fine; found /v1/responses emits reasoning despite parsing
  `exclude`. Filed: reasoning.exclude on Responses (484); overnight
  fence (485). 385–404 band +#2432/#2433 Shipped. Unparked sibling
  PR #2431 (restored pinned rows 19–28 / 6–8 after its band-row
  collapse failed the pin suite).

- **2026-11-22 pm (Neon + 1.112.0-dev.2 remainder + image data-policy)** —
  Mined Gemini 4 Neon GA ($3/$15, cache $0.15, `xhigh`), LiteLLM
  1.112.0-dev.2 leftovers (#52949 omit headers, #52972 Priority/
  cached-image billing), OpenRouter image/video `provider.zdr`/
  `data_collection` (11-13) against Dragos backdrop. Filed: Neon
  catalog (479); omit X-Daari headers (480); Priority/cached-image
  billing (481); image modality provider prefs (482); afternoon
  fence (483). Folded #52489 into open 426. Watch: semantic-router
  1.2.0 matched-utterances. Afternoon #2425 MCP secret re-resolve
  Shipped. Morning 474–478 unchanged.

- **2026-11-22 (OpenRouter data-policy incidents + 1.112.0-dev.2
  mined)** — Dragos/OR disclosure; Cache-Control; previous_response_id
  refuse; TTS duration; fence (474–478). Overnight 449 + #2272/#2273
  Shipped (#2415–#2417).

- **2026-11-21 (+pm)** — Linked billing + Flex wind-down + Ollama
  facade tools (464–468); pm refuse limits + TTS clone + Extractions
  BYOK (469–473). Extractions + MCP cancel / abandoned-stream /
  session pins Shipped.

- **2026-11-20 → 11-14** — Condensed: Fable 5.2 / 6.2 cache /
  introspect / deferred tools / Live (454–463); GPT-6.2 day-0 +
  Ultrafast (444–453); 1.110/1.111 Hydrogen/alerts (434–443);
  truncation honesty + vLLM 0.34 (424–433); BYOK + midstream +
  effective_to + thinking (405–423).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg /
  llama.cpp v1.0; CMA + 1.108.x; coding-router / Gemini 4 / Kong
  2.3.0 through Apache 2.0 and this PRD's creation. #2141 needs
  human close.
