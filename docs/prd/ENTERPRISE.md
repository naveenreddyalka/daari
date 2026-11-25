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

## Where daari stands (verified in-tree, 2026-11-24 night)

**Loop velocity.** Night main absorbed budget-reservation FinOps follow-through
(#2451 Grafana denials panel, #2452 doctor tip when `reserve_in_flight` lacks
USD windows). Earlier today: OCR/image deadlines (#2445), server-tool-fee Prom
(#2446), Fable/Mythos param_compat + ZDR retention honesty (#2437/#2438).
Open bands 474–493 still in flight.

**Outward.** Night delta: **OpenAI 11-24** — Healthcare model configurations on
`/v1/responses` (`gpt-6.2-astra-healthcare`, `gpt-6.2-sol-healthcare`,
`gpt-6-astra-healthcare`, `gpt-6.1-sol-healthcare`; medical-source web-search
index; Standard rates match general counterparts; Fast 2×; no Batch/Flex;
promo through ≥2026-12-31; PHI needs a separate BAA) and **chat-latest**
rolling snapshot refresh (prefer GPT-6.2 for production API). GPT-6.2
append-only `configuration_update` / `additional_tools` guidance remains the
prefix-preservation contract. LiteLLM still **1.110.3 / 1.109.4** + LTS
**1.108.16** (fold GA floor into open compare issues; do not re-file). Ollama
**0.40.18** facade-neutral. OpenRouter flat past provisional-providers on
guardrails. Kong 3.9.5 / AI GW 2.3.2; Portkey enterprise 2.33.1; vLLM 0.34.0;
1.112.0-dev.2 (Lens/FIPS) still pre-GA.

**Inward theme: healthcare day-0 ledger + Responses item honesty after
reservation ops shipped.** Longest-prefix pricing maps `*-healthcare` onto
parents and invents cache-write rates the specialized table omits; `/v1/models`
never lists the four ids; doctor never names BAA/medical-index; Responses
silently drops `configuration_update` / `additional_tools`. Reservation Grafana
+ doctor tip need a night fence.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 494 | Ship OpenAI healthcare catalog rates + capabilities (four `*-healthcare` ids; no invented cache-write; no Flex/Batch; Fast 2×; promo ≤2026-12-31) | 4 | 2 | OpenAI pricing / LiteLLM catalog | Day-0 on-box invoice for clinical pins; local tiers absorb cheap loops | Filed [#2453](https://github.com/naveenreddyalka/daari/issues/2453) |
| 495 | Doctor + docs: PHI/BAA honesty and medical-index web-search requirement for healthcare configs | 3 | 1 | OpenAI Help Center BAA notes | Preflight stops “model id = HIPAA” lies | Filed [#2454](https://github.com/naveenreddyalka/daari/issues/2454) |
| 496 | Honor `configuration_update` + `additional_tools` on `/v1/responses` — today non-message types are silently dropped | 4 | 2 | OpenAI Responses / Keep-prefix guide | Append-only GPT-6.2 clients keep wire shape through the edge | Filed [#2455](https://github.com/naveenreddyalka/daari/issues/2455) |
| 497 | Refresh `chat-latest` catalog note for the 2026-11-24 snapshot; steer production pins to GPT-6.2 | 2 | 1 | OpenAI changelog | Honest rolling-alias comment on-box | Filed [#2456](https://github.com/naveenreddyalka/daari/issues/2456) |
| 498 | Integration fence for the 11-24 night reservation-ops + healthcare follow-through wave | 2 | 2 | — (testability) | Hermetic 402 reservation denial + panel/doctor pins | Filed [#2457](https://github.com/naveenreddyalka/daari/issues/2457) |
| 491 | Honor `X-Daari-Deadline-Ms` on extractions / moderations / rerank / decisions | 3 | 2 | Kong request timeouts | One deadline arithmetic refuses before frontier spend | Filed [#2447](https://github.com/naveenreddyalka/daari/issues/2447) |
| 492 | Grafana panel for `daari_server_tool_cost_usd_total{tool}` | 2 | 1 | LiteLLM hosted analytics | Tool fees ≠ tokens; FinOps loop | Filed [#2448](https://github.com/naveenreddyalka/daari/issues/2448) |
| 493 | Integration fence for the 11-24 evening deadline-modality + tool-fee-metrics wave | 2 | 2 | — (testability) | Hermetic 504 + tool-fee settle | Filed [#2449](https://github.com/naveenreddyalka/daari/issues/2449) |
| 487 | Pin Claude Opus 4.5 deprecation lifecycle (retire 2027-01-22 → Opus 5.5) | 4 | 1 | Anthropic platform notes | `/v1/models` + doctor show the cutover | Filed [#2439](https://github.com/naveenreddyalka/daari/issues/2439) |
| 486 | EFS honesty for `models.retention_authorized` | 4 | 2 | Anthropic EFS console | Override is an honest EFS exception | Filed [#2440](https://github.com/naveenreddyalka/daari/issues/2440) |
| 489 | Prometheus + stats for `zdr_retention_required` refusals | 3 | 1 | LiteLLM spend/guardrail metrics | Graph impossible ZDR+Fable asks | Filed [#2441](https://github.com/naveenreddyalka/daari/issues/2441) |
| 488 | Promote LiteLLM LTS compare floor to **1.108.16** | 2 | 1 | LiteLLM LTS notes | Honest procurement floor | Filed [#2442](https://github.com/naveenreddyalka/daari/issues/2442) |
| 490 | Integration fence for Fable param_compat + ZDR retention + Opus/EFS wave | 2 | 2 | — (testability) | Hermetic overnight pins | Filed [#2443](https://github.com/naveenreddyalka/daari/issues/2443) |
| 484 | Honor `reasoning.exclude` on `/v1/responses` | 3 | 1 | OpenRouter /responses | Same strip as chat (#2433) | Filed [#2434](https://github.com/naveenreddyalka/daari/issues/2434) |
| 485 | Fence for OCR pages-billing + reasoning-object wave | 2 | 2 | — (testability) | Hermetic proof | Filed [#2435](https://github.com/naveenreddyalka/daari/issues/2435) |
| 479 | Ship Gemini 4 Neon catalog rates + capabilities + `xhigh` | 4 | 2 | Google AI Studio / LiteLLM | Day-0 ledger match | Filed [#2426](https://github.com/naveenreddyalka/daari/issues/2426) |
| 480 | Operator dial to omit `X-Daari-*` response headers | 3 | 2 | LiteLLM `include_litellm_headers` | Clean OpenAI-shaped surface | Filed [#2427](https://github.com/naveenreddyalka/daari/issues/2427) |
| 481 | Bill Priority rates + cached image tokens on image legs | 3 | 2 | LiteLLM 1.112.0-dev.2 | Priority vision matches invoice | Filed [#2428](https://github.com/naveenreddyalka/daari/issues/2428) |
| 482 | Honor OpenRouter `provider.zdr` / `data_collection` on image/video | 3 | 2 | OpenRouter native | One edge for data-policy | Filed [#2429](https://github.com/naveenreddyalka/daari/issues/2429) |
| 483 | Fence for MCP secret / Neon / omit-headers / image-priority wave | 2 | 2 | — (testability) | Hermetic proof | Filed [#2430](https://github.com/naveenreddyalka/daari/issues/2430) |
| 474 | Operator data-policy floor for marketplace legs | 4 | 2 | OpenRouter (reactive) | One on-box floor | Filed [#2418](https://github.com/naveenreddyalka/daari/issues/2418) |
| 475–478 | Cache-Control; refuse `previous_response_id`; TTS duration; fence | 2–3 | 1–2 | LiteLLM 1.112.0-dev.2 | RFC + loud refuse + duration math | Filed [#2419](https://github.com/naveenreddyalka/daari/issues/2419)–[#2422](https://github.com/naveenreddyalka/daari/issues/2422) |
| 469–473 | Linked-billing refuses; TTS `input_references`; Extractions BYOK; fence | 2–4 | 1–2 | Anthropic / OpenRouter | Bill-to + voice + tenant Extractions | Filed [#2409](https://github.com/naveenreddyalka/daari/issues/2409)–[#2413](https://github.com/naveenreddyalka/daari/issues/2413) |
| 464–468 | Server-tool replay; bill-to; Flex wind-down; Ollama facade tools; fence | 2–4 | 1–2 | LiteLLM / Anthropic / Ollama | Wire-shape + facade tool loop | Filed [#2402](https://github.com/naveenreddyalka/daari/issues/2402)–[#2406](https://github.com/naveenreddyalka/daari/issues/2406) |
| 459–463 | Deferred tools; Sol end **11-30**; Live catalog; exhausted-key; BYOK price fence | 2–4 | 1–3 | OpenRouter / OpenAI / LiteLLM | Agent + FinOps honesty | Filed [#2392](https://github.com/naveenreddyalka/daari/issues/2392)–[#2396](https://github.com/naveenreddyalka/daari/issues/2396) |
| 454–458 | Fable/Mythos param_compat; 6.2 chat-leg cache; introspect; stream no-dup; fence | 2–5 | 1–2 | LiteLLM / Anthropic | Flagship wire-shape | **454 Shipped** (#2437); open [#2385](https://github.com/naveenreddyalka/daari/issues/2385)–[#2388](https://github.com/naveenreddyalka/daari/issues/2388) |
| 449–453 | GPT-6.2 param_compat; Ultrafast; store:false; background windows; fence | 2–5 | 1–2 | OpenAI / LiteLLM | 6.2 day-0 + follow-through | **449 Shipped** (#2417); open [#2375](https://github.com/naveenreddyalka/daari/issues/2375)–[#2378](https://github.com/naveenreddyalka/daari/issues/2378) |
| 444–448 | GPT-6.2 catalog; SEP-3415; long-tool-name fence; speech discovery; fence | 2–4 | 1–3 | OpenAI / MCP | Day-0 catalog + Events | Filed [#2367](https://github.com/naveenreddyalka/daari/issues/2367)–[#2371](https://github.com/naveenreddyalka/daari/issues/2371) |
| 434–443 | successor_model; zero_retention; overload; Hydrogen; alerts; rate_limited_by; 1.111; fences | 2–4 | 1–3 | LiteLLM / Google | Tenancy + ops dials | Filed [#2346](https://github.com/naveenreddyalka/daari/issues/2346)–[#2363](https://github.com/naveenreddyalka/daari/issues/2363) |
| 424–433 | Truncated-cache; stream honesty; Responses `incomplete`; vLLM 0.34; 5xx/finish_reason Prom; HF; watermark | 2–4 | 1–3 | OpenAI / Kong / LiteLLM | Terminal + ops honesty | Filed [#2330](https://github.com/naveenreddyalka/daari/issues/2330)–[#2340](https://github.com/naveenreddyalka/daari/issues/2340) |
| 414–423 | Team BYOK modality + credential attribution + reconcile + binding Prom + auto_caching/residency + LTS + fences | 2–4 | 1–3 | LiteLLM / Portkey / Kong | Tenant credential + cache dials | Filed [#2313](https://github.com/naveenreddyalka/daari/issues/2313)–[#2325](https://github.com/naveenreddyalka/daari/issues/2325) |
| 409–413 | Midstream tool-call safety + truncation Prom/Grafana | 2–5 | 1–2 | LiteLLM 1.111-dev | Local loops must not double-fire | Open [#2304](https://github.com/naveenreddyalka/daari/issues/2304)/[#2306](https://github.com/naveenreddyalka/daari/issues/2306)/[#2307](https://github.com/naveenreddyalka/daari/issues/2307) |
| 405–408 | effective_to promos; Responses order; local thinking; fence | 2–4 | 2–3 | Kong / LiteLLM | Honest ledger + reasoning | Filed [#2297](https://github.com/naveenreddyalka/daari/issues/2297)–[#2300](https://github.com/naveenreddyalka/daari/issues/2300) |
| 385–404 | Extractions + OCR + reasoning + ZDR + deadlines + tool-fee ops; MCP cancel / pins / llama.cpp / refused-leg / cost panels | 2–4 | 1–3 | LiteLLM / OpenRouter / Kong / Anthropic | Same-box agent + FinOps | Open [#2269](https://github.com/naveenreddyalka/daari/issues/2269)–[#2291](https://github.com/naveenreddyalka/daari/issues/2291); Shipped #2265–#2268, #2272–#2273, #2398–#2401, #2415–#2416, #2432–#2433, **#2438**, **#2445–#2446**, **#2451–#2452** |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger meters; finish the console | Open (agent:working) |
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

Watch rows (do not file yet): **LiteLLM GA floor → 1.110.3** (fold into open
compare/LTS issues; 1.110.3/1.109.4 are backport patches — never file
separately); Ollama **0.40.18** (MLX/Metal only); **1.112.0-dev.2** remainder
(Lens, FIPS 140-3 image, custom spend windows — hold GA); OpenRouter
`allow_provisional_providers` (fold when OR guardrail authoring lands);
Anthropic EFS **webhook relay** (486 is docs/doctor only); MCP next
**2027-03-30**; Opus 4.8 fast removal **11-30**; Sol promo → $5/$30 on
**2026-11-30** (460 + 405); Astra/Sol for Law + Rosalind (Trusted Access —
demand-triggered with row 8 HIPAA BAA); incomplete synthetic-stream event
(fold 426); semantic-router 1.2.0; Kong OSS 3.9.5 + AI GW 2.3.2; vLLM 0.34
remainder; Portkey MCP policies; A2A 1.1 RC; SCIM + multi-issuer SSO;
Microsoft Web IQ `/v1/search`.

Verified fine this run — don't re-audit: budget reservation Grafana panel +
doctor tip (#2451/#2452); OCR/image deadline binding (#2445); server-tool-fee
Prom counters (#2446); overnight ZDR retention refuse (#2438); Fable/Mythos
param_compat (#2437); L0 × chat `reasoning.exclude`; per-request `provider.zdr`
fails closed (474 floor; 482 image wire).

---

## Path to enterprise-grade — next 5 milestones

1. **Billing + tenancy + data-policy + lifecycle + healthcare truth** —
   **healthcare catalog (494)** + **PHI/BAA honesty (495)**; Opus 4.5 lifecycle
   (487); EFS honesty (486); Neon (479); Priority/cached-image (481); image ZDR
   (482); marketplace floor (474); TTS duration (477); linked-billing (469–470);
   Extractions BYOK (472); Flex wind-down (466); Sol → 11-30 (460) + effective_to
   (405); Live catalog (461); zero_retention (435); deadline on remaining L6
   doors (491). Reservation ops + OCR/image deadlines shipped.
2. **Honest terminal outcomes + frontier wire-shape** —
   **`configuration_update` / `additional_tools` (496)**; reasoning.exclude on
   /v1/responses (484); previous_response_id refuse (476); store:false developer
   (451); Responses `incomplete` (426); truncated cache (424); stream honesty
   (425); overload envelopes (436). GPT-6.2 + Fable param_compat shipped.
3. **Nothing goes stale quietly** — **chat-latest 11-24 note (497)**;
   zdr_retention Prom (489); LTS 1.108.16 compare (488); tool-fee Grafana (492);
   omit X-Daari headers (480); Cache-Control (475); exhausted-key discovery
   (462); performance alerts (440); `rate_limited_by` (441); deprecation
   exposure (434); 5xx / auto_caching doctor+Prom (429–430, 419–420).
4. **Agent-protocol + tool-loop + voice fidelity** — TTS `input_references`
   (471); Ollama facade tools (467); deferred tools (459); MCP Events (445);
   Responses order + reasoning (406); local thinking (407).
5. **Local engine floor + discovery + honest compare + fences** — speech
   discovery (447); Live catalog (461); 1.111/1.112 watch (442); vLLM 0.34
   (427); fences through **498**; then 62–67.

---

## Changelog

- **2026-11-24 night (OpenAI healthcare + Responses items; reservation ops)** —
  Outward: OpenAI healthcare model configurations + chat-latest snapshot
  refresh; GPT-6.2 keep-prefix `configuration_update` / `additional_tools`
  still dropped on-box. Competitors otherwise flat vs pm (LiteLLM 1.110.3,
  Ollama 0.40.18). Inward: audited #2451/#2452; longest-prefix invents
  healthcare cache-writes; no BAA doctor tip. Filed: healthcare catalog (494);
  PHI/BAA honesty (495); configuration_update/additional_tools (496);
  chat-latest note (497); night fence (498). 385–404 band +#2451/#2452 Shipped.

- **2026-11-24 pm (deadline doors + tool-fee panel; sibling unpark)** —
  Unparked morning PR. LiteLLM 1.110.3/1.109.4; Ollama 0.40.18. Filed
  deadline on remaining L6 doors (491); tool-fee panel (492); evening fence
  (493). #2445/#2446 Shipped.

- **2026-11-24 (Anthropic EFS + Opus 4.5 + LiteLLM 1.108.16)** — Filed Opus
  lifecycle (487); EFS doctor/docs (486); zdr_retention Prom (489); LTS
  1.108.16 (488); overnight fence (490). 454 + #2284 Shipped.

- **2026-11-23 → 11-14** — Condensed: reasoning.exclude (484–485); Neon /
  omit headers / Priority image / image ZDR (479–483); OR data-policy +
  Cache-Control + TTS (474–478); linked billing + Flex + facade tools
  (464–473); Fable/6.2/deferred/Live (454–463); GPT-6.2 day-0 (444–453);
  1.110/Hydrogen/alerts (434–443); truncation + vLLM (424–433); BYOK +
  midstream + thinking (405–423).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg / llama.cpp
  v1.0; CMA + 1.108.x; coding-router / Gemini 4 / Kong 2.3.0 through Apache
  2.0 and this PRD's creation. #2141 needs human close.
