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

## Where daari stands (verified in-tree, 2026-11-25 evening)

**Loop velocity.** Morning prd-cycle filed 499–502 (tenant-BYOK breaker,
`context_management`, LiteLLM 1.111.0 compare floor, overnight fence) and
merged. Overnight main still owns 405–407 + midstream panel (#2459–#2462).
Open bands 474–502 still in flight.

**Outward (delta since morning).** Competitors otherwise flat: LiteLLM still
**1.111.0 GA** + **1.112.0-rc.1** (FOCUS 1.5 schema break + control plane +
priority queues — hold GA beyond the filed floor); Portkey 2.34.1;
OpenRouter 11-24 wire still the newest (Batches `/results`, speech
`output_delivery`, BYOK `is_exclusive`). OpenAI model card reconfirmed:
**GPT-5.6 Sol promo through 2026-11-30**. Google AI Studio: **Carbon/Argon
intro $2/$10 through 2026-11-30**, list from Dec 1. Ollama 0.40.18 / vLLM
0.34 / Kong AI GW 2.3.2 unchanged.

**Inward theme: promo-window honesty now that `effective_to` ships.**
Verified 2026-11-25: `resolve_price("gpt-5.6-sol")` → **$5/$30** because
catalog `effective_to` is still **2026-11-21** — OpenAI invoice is still
$4/$20 until Nov 30 (~25%/50% overbill). `gemini-4-carbon` /
`gemini-4-argon` ship Dec-1 list with **no** promo window — Google still
lists intro $2/$10 through Nov 30 (2× overbill). Speech drops
`output_delivery`; batches have no `GET …/results`. Morning breaker /
`context_management` gaps remain open.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 503 | Move `gpt-5.6` / `gpt-5.6-sol` `effective_to` to **2026-11-30** — catalog already bills baseline while OpenAI promo is live | 5 | 1 | OpenAI model card / pricing | Day-accurate on-box ledger; wrong cliff kills savings trust | Filed [#2468](https://github.com/naveenreddyalka/daari/issues/2468) |
| 504 | Gemini 4 Carbon/Argon intro $2/$10/$0.10 through 2026-11-30 via `effective_to` + Dec-1 baseline — catalog already at list | 4 | 1 | Google AI Studio pricing | Same time-bounded engine as Sol; stop 2× overbill | Filed [#2469](https://github.com/naveenreddyalka/daari/issues/2469) |
| 505 | Honor speech `output_delivery` (`stream` / `url` via FileStore; ZDR → stream) | 3 | 2 | OpenRouter TTS | Local FileStore URLs, not vendor blob | Filed [#2470](https://github.com/naveenreddyalka/daari/issues/2470) |
| 506 | `GET /v1/batches/{id}/results` JSONL convenience (OpenRouter 11-24) | 3 | 2 | OpenRouter Batches | Same on-box output_file bytes; one hop for OR SDK | Filed [#2471](https://github.com/naveenreddyalka/daari/issues/2471) |
| 507 | Integration fence for the 11-25 evening promo-window + speech/batches wave | 2 | 2 | — (testability) | Hermetic FinOps + wire-shape pins | Filed [#2472](https://github.com/naveenreddyalka/daari/issues/2472) |
| 499 | Tenant-BYOK auth failures must not open the **shared** frontier slot breaker | 4 | 2 | LiteLLM 1.112.0-rc.1 (#53431) | Credential source known on-box | Filed [#2463](https://github.com/naveenreddyalka/daari/issues/2463) |
| 500 | Honor `context_management` on `/v1/responses` | 3 | 2 | OpenRouter /responses | `compact_to_fit` + `/compact` already on-box | Filed [#2464](https://github.com/naveenreddyalka/daari/issues/2464) |
| 501 | Promote compare floor to **LiteLLM 1.111.0 GA + 1.108.17 LTS** | 2 | 1 | LiteLLM release notes | Parity predates the GA | Filed [#2465](https://github.com/naveenreddyalka/daari/issues/2465) |
| 502 | Integration fence for the 11-24/11-25 overnight wave | 2 | 2 | — (testability) | Hermetic cross-door pins | Filed [#2466](https://github.com/naveenreddyalka/daari/issues/2466) |
| 494–498 | Healthcare catalog; PHI/BAA doctor; `configuration_update`/`additional_tools`; chat-latest note; night fence | 2–4 | 1–2 | OpenAI / Keep-prefix | Clinical pins + Responses item honesty | Filed [#2453](https://github.com/naveenreddyalka/daari/issues/2453)–[#2457](https://github.com/naveenreddyalka/daari/issues/2457) |
| 491–493 | Deadline on remaining L6 doors; tool-fee Grafana; evening fence | 2–3 | 1–2 | Kong / LiteLLM | One deadline arithmetic + FinOps | Filed [#2447](https://github.com/naveenreddyalka/daari/issues/2447)–[#2449](https://github.com/naveenreddyalka/daari/issues/2449) |
| 486–490 | Opus 4.5 lifecycle; EFS honesty; zdr_retention Prom; LTS 1.108.16; fence | 2–4 | 1–2 | Anthropic / LiteLLM | Cutover + retention truth | Filed [#2439](https://github.com/naveenreddyalka/daari/issues/2439)–[#2443](https://github.com/naveenreddyalka/daari/issues/2443) |
| 479–485 | Neon; omit headers; Priority image; image ZDR; fence; reasoning.exclude; OCR fence | 2–4 | 1–2 | Google / LiteLLM / OpenRouter | Catalog + wire-shape | Filed [#2426](https://github.com/naveenreddyalka/daari/issues/2426)–[#2435](https://github.com/naveenreddyalka/daari/issues/2435) |
| 474–478 | Marketplace data-policy floor; Cache-Control; previous_response_id refuse; TTS duration; fence | 2–4 | 1–2 | OpenRouter / LiteLLM | Policy + duration math | Filed [#2418](https://github.com/naveenreddyalka/daari/issues/2418)–[#2422](https://github.com/naveenreddyalka/daari/issues/2422) |
| 459–473 | Deferred tools; Sol end; Live; exhausted-key; BYOK fence; linked-billing; TTS refs; Extractions BYOK; facade tools; Flex; fences | 2–4 | 1–3 | OpenRouter / OpenAI / Anthropic | Agent + FinOps honesty | Filed [#2392](https://github.com/naveenreddyalka/daari/issues/2392)–[#2413](https://github.com/naveenreddyalka/daari/issues/2413) |
| 444–458 | GPT-6.2 / Fable day-0 + param_compat follow-through | 2–5 | 1–2 | OpenAI / LiteLLM / Anthropic | Flagship wire-shape | **449/454 Shipped**; open [#2367](https://github.com/naveenreddyalka/daari/issues/2367)–[#2388](https://github.com/naveenreddyalka/daari/issues/2388) |
| 405–443 | effective_to; reasoning order; local thinking; midstream; BYOK tenancy; truncation; vLLM; ops dials | 2–5 | 1–3 | LiteLLM / Kong / OpenAI | Honest ledger + ops | **405–407 + midstream panel Shipped**; open through [#2363](https://github.com/naveenreddyalka/daari/issues/2363) |
| 385–404 | Extractions / OCR / reasoning / ZDR / deadlines / tool-fee / MCP / llama.cpp | 2–4 | 1–3 | LiteLLM / OpenRouter / Kong | Same-box agent + FinOps | Open [#2269](https://github.com/naveenreddyalka/daari/issues/2269)–[#2291](https://github.com/naveenreddyalka/daari/issues/2291); many Shipped |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Shipped (#1288) | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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

Watch rows (do not file yet): **1.112.0-rc.1** remainder (control plane,
gpt-live-1 WebRTC, priority queues, Lens, FIPS 140-3, **FOCUS 1.5**
`ServiceProviderName` export — hold GA; 501 covers the 1.111.0 floor);
Portkey MCP OAuth `extra_token_params` (mint already sends
scope/audience/resource); OpenRouter BYOK `is_exclusive` + guardrail
`allow_safety_retention_openai` (fold with retention honesty); OpenRouter
`allow_provisional_providers`; Anthropic EFS webhook relay; MCP next
**2027-03-30**; Opus 4.8 fast removal **11-30** (lifecycle shield shipped);
Sol promo → baseline on **2026-11-30** (503 fixes the cliff; docs-only
honesty sibling remains); Astra/Sol for Law + Rosalind (row 8);
semantic-router / Kong / vLLM / A2A / SCIM / Web IQ — demand-triggered.

Verified fine this run — don't re-audit: per-key-per-model rpm/tpm/rpd/tpd
(#1592/#2240); `prompt_cache_key`/`prompt_cache_options`; session pin
prefix-hash (#2267); oauth mint scope/audience/resource; budget reservation
Grafana + doctor (#2451/#2452); ZDR retention refuse (#2438); Opus 4.8
speed lifecycle shield (#2053); morning 499–502 filing still accurate.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing truth this week** — **Sol/5.6 `effective_to` → Nov 30 (503)**;
   **Carbon/Argon intro window (504)**; healthcare catalog (494); Opus 4.5
   lifecycle (487); Neon (479); Priority/cached-image (481); marketplace
   floor (474); Sol docs honesty sibling; Flex wind-down (466).
2. **Tenancy + data-policy blast radius** — tenant-BYOK breaker (499); EFS
   honesty (486); image ZDR (482); Extractions BYOK (472); zero_retention
   (435); deadline on remaining L6 doors (491).
3. **Frontier wire-shape** — `context_management` (500); speech
   `output_delivery` (505); batches `/results` (506);
   `configuration_update`/`additional_tools` (496); reasoning.exclude (484);
   previous_response_id refuse (476); Responses `incomplete` (426).
4. **Nothing goes stale quietly** — compare 1.111.0 floor (501); chat-latest
   note (497); zdr_retention Prom (489); tool-fee Grafana (492); omit
   headers (480); Cache-Control (475); performance alerts (440).
5. **Agent-protocol + local floor + fences** — TTS refs (471); facade tools
   (467); deferred tools (459); MCP Events (445); vLLM 0.34 (427); fences
   through **507**; then 62–67.

---

## Changelog

- **2026-11-25 evening (promo-window honesty + OpenRouter speech/batches)** —
  Outward flat vs morning (LiteLLM 1.111.0 / 1.112.0-rc.1; Portkey 2.34.1;
  OR 11-24). Inward: after `effective_to` shipped, Sol/5.6 cliff still at
  Nov 21 while OpenAI promo runs through Nov 30; Carbon/Argon catalog at
  Dec-1 list with no intro window; speech drops `output_delivery`; no
  batches `/results`. Filed: Sol effective_to fix (503); Carbon/Argon
  intro window (504); speech output_delivery (505); batches results (506);
  evening fence (507).

- **2026-11-25 (LiteLLM 1.111.0 GA; tenant-BYOK breaker blast radius)** —
  Filed breaker scoping (499); context_management (500); compare 1.111.0
  floor (501); overnight fence (502). 405–407 + midstream panel Shipped.

- **2026-11-24 night → 11-14** — Condensed: healthcare + Responses items
  (494–498); deadline/tool-fee (491–493); Opus/EFS/ZDR (486–490);
  Neon/omit-headers/Priority image (479–485); OR data-policy + TTS
  (474–478); linked billing + Flex + facade (464–473); Fable/6.2/Live
  (444–463); 1.110/Hydrogen/alerts (434–443); truncation + vLLM
  (424–433); BYOK + midstream + thinking (405–423).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg /
  llama.cpp; CMA + 1.108.x; coding-router / Gemini 4 / Kong through
  Apache 2.0 and this PRD's creation.
