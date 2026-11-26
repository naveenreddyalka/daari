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

## Where daari stands (verified in-tree, 2026-11-26)

**Loop velocity.** Overnight/morning autodev drained the promo-window cliff
(Sol/5.6 + Carbon/Argon `effective_to`), hot-reload, end-user inventory,
guardrail profiles, nested multi-agent usage, and a stack of BYOK / spend /
Prom panels. Open bands 474–507 plus stalled-merge regressions still in flight.

**Outward (delta since 11-25 evening).** LiteLLM published
**1.113.0-dev.1** (2026-11-26): require customer headers by gateway/team/key,
Codex `compaction_trigger` on the chat bridge, aac/flac speech length billing,
Redis-shared router cooldowns, Lens agent spans, Meta Muse / Gemini Live
Avatar — **hold GA**; stable floor remains **1.111.0** + **1.112.0-rc.1**
(FOCUS 1.5 / control plane / priority queues). Portkey Enterprise Gateway
**2.34.1** (MCP `extra_token_params`). OpenRouter still newest on the 11-24
wire (`is_exclusive`, `output_delivery`, batches `/results`); SDK follow-ups
only (wav enum, `creator_user_id` on keys). Ollama **0.40.18** stable;
**0.40.19-rc0** pre-release (hold). Kong AI GW / vLLM otherwise flat.

**Inward theme: tenancy exclusivity + IdP/header floors after promo truth.**
Sol/Carbon cliffs **Shipped**. Next failure mode is soft tenancy: BYOK that
still falls through to the shared pool, global-only header policy, OAuth mint
without arbitrary AS form fields, and no provisional-provider floor on
marketplace legs. Chat-bridge `compaction_trigger` is the Codex wire gap
beside open `context_management`.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 508 | BYOK `is_exclusive` — exclusive frontier credentials must not fall through to the shared pool | 4 | 2 | OpenRouter BYOK | On-box credential source; fail closed vs surprise org invoice | Filed [#2510](https://github.com/naveenreddyalka/daari/issues/2510) |
| 509 | Per-key / per-team required customer headers (beyond global `server.header_policy`) | 4 | 2 | LiteLLM 1.113.0-dev.1 (#53045) | Chargeback headers without SaaS control plane | Filed [#2511](https://github.com/naveenreddyalka/daari/issues/2511) |
| 510 | OAuth mint `extra_token_params` for client-credentials IdPs | 3 | 1 | Portkey 2.34.1 | Secrets stay local; Entra-class AS quirks | Filed [#2512](https://github.com/naveenreddyalka/daari/issues/2512) |
| 511 | `allow_provisional_providers` dial on marketplace / OpenRouter legs | 3 | 2 | OpenRouter guardrails | Operator floor after provider incidents | Filed [#2513](https://github.com/naveenreddyalka/daari/issues/2513) |
| 512 | Honor Codex `compaction_trigger` on the chat-completions bridge | 3 | 2 | LiteLLM 1.113 (#53266) | Local `compact_to_fit` before L6 | Filed [#2514](https://github.com/naveenreddyalka/daari/issues/2514) |
| 505–507 | Speech `output_delivery`; batches `/results`; evening fence | 2–3 | 2 | OpenRouter TTS/Batches | Local FileStore + hermetic pins | Open [#2470](https://github.com/naveenreddyalka/daari/issues/2470)–[#2472](https://github.com/naveenreddyalka/daari/issues/2472) |
| 503–504 | Sol/5.6 + Carbon/Argon promo `effective_to` cliffs | 4–5 | 1 | OpenAI / Google pricing | Day-accurate on-box ledger | **Shipped** |
| 499–502 | Tenant-BYOK breaker; `context_management`; compare 1.111.0; overnight fence | 2–4 | 1–2 | LiteLLM / OpenRouter | Credential blast radius + wire-shape | Open [#2463](https://github.com/naveenreddyalka/daari/issues/2463)–[#2466](https://github.com/naveenreddyalka/daari/issues/2466) |
| 494–498 | Healthcare catalog; PHI/BAA; `configuration_update`; chat-latest; night fence | 2–4 | 1–2 | OpenAI | Clinical pins + Responses honesty | Open [#2453](https://github.com/naveenreddyalka/daari/issues/2453)–[#2457](https://github.com/naveenreddyalka/daari/issues/2457) |
| 474–493 | Marketplace data-policy; TTS duration; deadlines; Opus/EFS; Neon; fences | 2–4 | 1–2 | OR / LiteLLM / Anthropic | Policy + FinOps | Open bands; Opus 4.5 lifecycle **Shipped** |
| 444–473 | GPT-6.2 / Fable / Live / Extractions / Flex / facade tools | 2–5 | 1–3 | OpenAI / OR / Anthropic | Flagship + agent honesty | Open through mid-2300s; many Shipped |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger meters; finish the console | **Inventory + profiles + nested usage Shipped**; web-ui pagination still open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | **Shipped** | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **1.112.0-rc.1 / 1.113.0-dev.1** remainder
(control plane, gpt-live-1 WebRTC, priority queues, Lens, FIPS 140-3,
Redis-shared cooldowns, Meta Muse / Live Avatar, **FOCUS 1.5**
`ServiceProviderName` — hold GA; compare floor issue covers 1.111.0);
OpenRouter `allow_safety_retention_*` (fold with retention honesty);
OpenRouter `creator_user_id` keys filter; Anthropic EFS webhook relay;
MCP next **2027-03-30**; Opus 4.8 fast removal **11-30** (lifecycle shield
shipped); Sol promo → baseline on **2026-11-30** (cliff shipped; docs
honesty sibling still open); Ollama **0.40.19** until GA; Astra/Sol for
Law + Rosalind (row 8); semantic-router / Kong / vLLM / A2A / SCIM / Web IQ
— demand-triggered.

Verified fine this run — don't re-audit: Sol/Carbon `effective_to` windows;
hot-reload; end-user inventory + guardrail profiles; nested multi-agent
usage; per-key-per-model rpm/tpm/rpd/tpd; `prompt_cache_key` /
`prompt_cache_options`; session pin prefix-hash; oauth mint
scope/audience/resource (extra params is the new gap); budget reservation
Grafana + doctor; ZDR retention refuse; Opus 4.8 speed lifecycle shield;
global `server.header_policy` (per-key overlay is the new gap).

---

## Path to enterprise-grade — next 5 milestones

1. **Tenancy exclusivity + attribution floors** — BYOK `is_exclusive` (508);
   per-key/team required headers (509); tenant-BYOK breaker (499); Extractions
   BYOK; linked-billing refuses; zero_retention dials.
2. **Marketplace / IdP honesty** — provisional-providers dial (511); OAuth
   `extra_token_params` (510); data-policy floor (474); EFS honesty; image ZDR.
3. **Frontier wire-shape** — `compaction_trigger` chat bridge (512);
   `context_management` (500); speech `output_delivery` (505); batches
   `/results` (506); `configuration_update` / reasoning.exclude /
   previous_response_id refuse.
4. **Billing + compare freshness** — TTS duration (2421 track); healthcare
   catalog; Neon / Priority image; compare 1.111.0 floor; Sol docs honesty
   sibling; hold 1.113-dev / FOCUS 1.5 until GA.
5. **Ops + fences + console** — fences through 507 + new wave; tool-fee /
   zdr_retention Prom; web-ui pagination (62–67 remainder); then demand-
   triggered row 8.

---

## Changelog

- **2026-11-26 (LiteLLM 1.113-dev.1; Portkey 2.34.1; BYOK exclusivity)** —
  Outward: LiteLLM 1.113.0-dev.1 (customer headers, compaction_trigger,
  speech length, Redis cooldowns — hold GA); Portkey 2.34.1
  `extra_token_params`; OR/Ollama otherwise flat vs evening. Inward: Sol/
  Carbon cliffs + hot-reload + end-user inventory + guardrail profiles
  Shipped. Filed: BYOK is_exclusive (508); per-key required headers (509);
  OAuth extra_token_params (510); provisional-providers dial (511);
  compaction_trigger chat bridge (512).

- **2026-11-25 evening (promo-window honesty + OpenRouter speech/batches)** —
  Filed Sol effective_to (503); Carbon/Argon intro (504); speech
  output_delivery (505); batches results (506); evening fence (507).

- **2026-11-25 (LiteLLM 1.111.0 GA; tenant-BYOK breaker blast radius)** —
  Filed breaker scoping (499); context_management (500); compare 1.111.0
  floor (501); overnight fence (502).

- **2026-11-24 night → 11-14** — Condensed: healthcare + Responses items
  (494–498); deadline/tool-fee (491–493); Opus/EFS/ZDR (486–490);
  Neon/omit-headers/Priority image (479–485); OR data-policy + TTS
  (474–478); linked billing + Flex + facade (464–473); Fable/6.2/Live
  (444–463); 1.110/Hydrogen/alerts (434–443); truncation + vLLM
  (424–433); BYOK + midstream + thinking (405–423).

- **2026-11-13 → 10-28** — Condensed: Extractions / refused-leg /
  llama.cpp; CMA + 1.108.x; coding-router / Gemini 4 / Kong through
  Apache 2.0 and this PRD's creation.
