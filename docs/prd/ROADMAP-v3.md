# daari — Roadmap v3: ahead of OpenRouter

> **Status:** Active — supersedes [ROADMAP-v2.md](ROADMAP-v2.md) for *what to build next*  
> **Date:** 2026-08-26  
> **Trigger:** Stripe agreed to acquire OpenRouter (terms undisclosed; Reuters reported ~$8B). Agent traffic on that network now burns ~5× the tokens of a human on the same model.  
> **Sources:** [Stripe / OpenRouter](https://www.artificialintelligence-news.com/news/stripe-openrouter-acquisition-ai-model-routing/), [agent token economics](https://ppc.land/ai-agents-use-five-times-more-tokens-than-humans-openrouter-data-shows/), [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [ZDR](https://openrouter.ai/docs/guides/features/zdr), [BYOK](https://openrouter.ai/docs/guides/overview/auth/byok), live daari benches on Apple M4 Pro (Ollama 0.18.2).

v2 already shipped the gateway-parity trains (Responses API, virtual keys, Redis/Helm, guardrails). The remaining v2 leftovers are real but they are **not** why we are behind OpenRouter. This document is the competitive plan.

---

## 1. The category error

OpenRouter is a **hosted marketplace**: one key, 400+ models, 80+ providers, prepaid credits, live endpoint telemetry, Stripe-grade billing. Stripe bought that because tokens are becoming a unit of commerce (usage, credits, cached vs generated, per-model price tables).

daari is a **local-first execution router**: cache → rules → tools → small local models → frontier last. We do not have 10 million developers or 10 trillion tokens/day. We will not win by cloning a catalog Stripe just paid billions for.

We lose today because **Cursor / Claude Code / agents already talk like OpenRouter customers** (one OpenAI-shaped URL, tools on every turn, huge system prompts) and we **refuse the cache on exactly that traffic** (ADR-0004: agent turns skip L0). OpenRouter’s own data says >85% of agent token burn is *re-reading* cached prompts. That is our product, and we turn it off for agents.

| | OpenRouter | daari today |
|--|------------|-------------|
| Default inference | Remote, paid | On-device, $0 if it hits L0–L5 |
| Catalog | 400+ models / 80+ providers | Ollama + optional L6 list |
| Same-model provider pick | Price / latency / throughput, live | Single `base_url` per slot |
| Failover | Outage, 429, context, moderation | Bounded HTTP retries + circuit breaker |
| Privacy controls | `zdr`, `data_collection`, EU pin | Local-by-default; no ZDR object on L6 |
| Agent cache | Provider prompt-cache (billed cheaper) | L0/L1 **skipped** when `tools` present |
| Billing | Credits, BYOK, native tokenizers, `usage.cost` | Ledger + gpt-4o *implied* price |
| Distribution | Hosted, one key, playground | `daari serve` on the laptop |

If we try to “be OpenRouter,” we lose. If we make **agent turns cheaper than OpenRouter by not leaving the machine**, we are the product Stripe cannot buy.

---

## 2. What OpenRouter can do that we cannot

Request-body `provider` object (Chat Completions):

| Field | What it does | daari |
|-------|----------------|-------|
| `order` / `only` / `ignore` | Pin or skip provider slugs | Partial: ordered `frontier.providers` in config, not per-request |
| `allow_fallbacks` | Backup endpoints when primary dies | Circuit breaker on slots; no request flag |
| `sort`: `price` \| `throughput` \| `latency` | Reorder live endpoints | No live endpoint telemetry |
| `preferred_min_throughput` / `preferred_max_latency` | p50–p99 cuts | No |
| `max_price` | Cap $/M tokens | Daily/monthly USD budget only |
| `require_parameters` | Skip endpoints that cannot honor tools / max_tokens | Capability catalog is local-only |
| `data_collection` | Deny providers that store/train | No |
| `zdr` | Zero Data Retention endpoints only | No |
| `quantizations` | int4 / int8 filter | No |
| EU / US residency | Enterprise in-region | No |
| `:nitro` / `:floor` model suffixes | Throughput vs cheapest | No aliases |
| BYOK | User’s OpenAI/Anthropic/… keys, OR credits as fallback | Keys in env / virtual keys; no marketplace mix |
| Plugins (web search, etc.) | Third-party tools on the route | MCP egress exists; no search plugin |
| `usage` split | prompt / completion / reasoning / cached + **cost** + upstream cost | prompt/completion; cache_hit bool; no reasoning/cached/cost |
| Native tokenizer | Per-model counts | Provider-reported or chars/4 |
| Public `/models` + rankings | Live catalog | Local + configured models |
| Guardrails as routing policy | ZDR per key / org member | Guardrails exist; not bound to provider pick |

Measured market facts we must treat as constraints, not goals:

- 400+ models, 80+ providers, 10M+ developers, >10T tokens/day (Stripe / OpenRouter, Aug 2026).
- Same model, 10× price spread across providers (Llama 3.3 70B: $0.10 vs $1.04 / M input, Jun 2026).
- Agents ≈ 5× human tokens; 14× agent volume since Feb 2026; >85% of that is cached-prompt reread.
- Snowflake Cortex, Cloudflare AI Gateway, Bedrock Intelligent Prompt Routing, Azure Foundry all added *dynamic model routing* in the same window. Routing is table stakes. **Local $0 + trusted cache** is not.

---

## 3. What we can do that OpenRouter cannot

These are already shipped. They are not marketed as the answer to the Stripe deal.

| Capability | Evidence |
|------------|----------|
| Exact L0 replay at **320 rps / 61 ms p95 / 100% hit** | `docs/developer/resources/benchmark-load.md` (M4 Pro) |
| Generate-heavy still **$0** on device | same page: 5.0 rps, max_tokens=8, no cache |
| vs LiteLLM on the same Ollama: **~27×** on $0 tiers | `benchmark-vs-litellm.md` |
| vs raw Ollama: **43×** median on cache hits | `benchmark-comparison.md` |
| Cache *trust* (near-miss reject 100%, paraphrase retention published) | live product bench |
| Lt / CCS — git, lint, pytest without a model | router |
| IDE one-click (Cursor, Claude Code, JetBrains facade, VS Code) | setup recipes |
| Code never leaves the machine on L0–L5 | default `X-Daari-No-Frontier` path |

OpenRouter cannot offer a 320 rps L0 hit on the developer’s laptop. They can only discount the *re-read* at the provider. We should make the re-read **free and local**.

---

## 4. Why we have been slow

Not a talent problem. A **queue** problem.

1. **v2 declared OpenRouter “nothing structural”** and parked marketplace work. Correct as a non-goal; wrong as “ignore their API and their agent-token data.”
2. **auto-dev picks oldest P3** (OIDC `kty`, `validate_assignment`) after P1/P2 emptied. Those fixes are real. They do not move a Cursor user off OpenRouter.
3. **ADR-0004** made the highest-volume client path (tools on every turn) uncacheable. That was right for “don’t serve a stale tool result.” It is wrong as a blanket skip of L0/L1 on the *prompt prefix*.
4. **We measure Ask-shaped benches** (short chat, no tools). The market is agents. Our published numbers do not show the 5× token problem.
5. **L6 through OpenRouter is a `base_url`**, not a product: we do not pass `provider`, ZDR, sort, or cost.

Until the backlog’s top card is “agent tokens stay on the machine,” we will look like a slower LiteLLM.

---

## 5. Trains (build these, in this order)

### G1 — Agent prefix cache (the Stripe-deal answer)

**Outcome:** A Cursor agent turn that only grew the last tool result hits L0/L1 on the stable prefix (system + tools + history hash), instead of skipping cache entirely.

- Split ADR-0004: still do not cache *final tool-call transcripts* as if they were Ask answers; **do** cache prefix embeddings / exact prefix keys.
- Honor provider prompt-cache headers on L6 (Anthropic `cache_control`, OpenAI automatic prefix).
- Publish an **agent mix** on the load harness: N tool-bearing turns, report cached-input tokens avoided vs a raw OpenRouter path (priced, not billed).
- Default-suite tests: tool-bearing request with identical prefix → L0 or L1 hit; changed last tool result → miss on suffix only.

**Done when:** live agent mix shows ≥50% of prompt tokens served at L0/L1 or as local prefix, and the published page says so.

### G2 — OpenRouter-shaped L6 provider object

**Outcome:** The same JSON Cursor already sends to OpenRouter (`provider.order`, `sort`, `zdr`, `data_collection`, `max_price`, `allow_fallbacks`) is honored when daari escalates to L6.

- Parse `provider` on OpenAI + Anthropic adapters; store on `InternalRequest`.
- Map onto `frontier.providers` slots + OpenRouter passthrough when the slot `base_url` is OpenRouter.
- Fail closed: if `zdr: true` and no slot declares ZDR, 4xx — do not silently drop the constraint.
- Surface `usage.cost`, cached tokens, and chosen provider in `daari_meta`.

**Done when:** a fixture request with `provider: { zdr: true, sort: "price" }` is visible in traces and rejected or routed correctly; OpenRouter integration test (mocked HTTP) covers passthrough.

### G3 — First-class OpenRouter backend (use them, don’t clone them)

**Outcome:** `frontier.providers[].id: openrouter` is documented, tested, and the default L6 hop — BYOK keys still win when set.

- Official slot template + `openrouter/auto` and explicit model slugs.
- Forward `HTTP-Referer` / title so app attribution works.
- Record **upstream cost vs daari cost** (local = $0) on every L6 row.
- `:floor` / `:nitro` on the **local** side as aliases: floor = smallest capable local tier; nitro = warmest / lowest-latency local backend (we already have warm-model preference).

**Done when:** docs + mocked test + one live optional test (`OPENROUTER_API_KEY`) that is skipped in CI.

### G4 — Cost-of-pass routing (stop sending every task to the biggest model)

**Outcome:** Published eval: expected $ and ms to a *correct* answer by task class, not just “we routed to L3.”

- Extend the live bench with a **cost-of-pass** column (retry until match or cap).
- Wire latency budget + capability catalog into the default Ask/Agent split so brand-safety / classify / “say hi” never touch L6.
- Dashboard: % of agent prompt tokens that never left the device.

**Done when:** `benchmarks.md` has a cost-of-pass table and TRACKING records the $0-tier rate on an *agent* corpus, not only GP-01–20.

### G5 — Availability the IDE actually feels

**Outcome:** When Ollama is cold, L4 is down, or L6 429s, the client still gets a well-formed stream — and we say which fallback fired.

- Failover reasons OpenRouter lists: outage, rate limit, context-length, moderation. We retry HTTP; we do not yet remap “context too long” → compress / drop to a long-context slot.
- `/v1/models` lists local + L6 with capability tags (tools, json, vision, zdr).
- Watchdog: replace the brittle `twenty` live assertion (#213/#217/#220) so main E2E stops filing noise.

**Done when:** a context-length error on L3 escalates to L4/L5 or compresses, traced; the three watchdog issues are closed.

### G6 — v2 leftovers (do not let these jump the queue)

Still worth doing, **after** G1–G3: B2/B3 boundaries (#172), extension content script (#171), IdP-minted keys (#176), multi-window budgets (#174), synonym verifier (#208), silent conflicted auto-merge (#200). These are product, not the OpenRouter gap.

---

## 6. Non-goals (still)

- Hosted SaaS marketplace, prepaid credit ledger, public model rankings.
- Training foundation models.
- Matching 400-model SKU coverage on our GPU.
- Replacing Stripe billing.

---

## 7. Ninety-day sequence

| Window | Train | Why this first |
|--------|-------|----------------|
| Days 1–21 | **G1** agent prefix cache + agent bench page | This is the 85% token pile |
| Days 22–45 | **G2** + **G3** provider object + OpenRouter slot | Drop-in for teams that already have an OR key |
| Days 46–70 | **G4** cost-of-pass + agent $0-tier in TRACKING | The number we put on the homepage |
| Days 71–90 | **G5** failover + models list + watchdog hygiene | Feels like a platform |

auto-dev rule change: **P1 cards on this file outrank oldest P3.** If the queue is empty of G1–G5, then P3.

---

## 8. Success metrics (not vanity)

- Agent-mix **$0-tier rate** ≥ 70% of prompt tokens on the published corpus.
- Agent-mix **implied frontier spend avoided** published next to the LiteLLM page.
- L6 OpenRouter passthrough: `zdr` / `sort` / `max_price` honored or hard-fail.
- Zero new “twenty” watchdog issues; live `max_tokens` test binds on `usage` + `finish_reason`.
- Homepage / compare page leads with OpenRouter, not only LiteLLM.

---

## Related

- [ROADMAP-v2.md](ROADMAP-v2.md) — F1–F6 shipped / leftover  
- [compare.md](../developer/resources/compare.md)  
- [04-competitive-landscape.md](../discovery/04-competitive-landscape.md)  
- ADR-0004 (Ask vs Agent) — amend under G1, do not delete  
