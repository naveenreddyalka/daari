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

## Where daari stands (verified in-tree, 2026-11-27)

**Loop velocity.** Same-day merges closed web-ui key/team pagination +
`report.users`, per-key/team `zero_retention`, typed overload envelopes,
`rate_limited_by` on 429s, spend/traffic/latency/error alerts, Hydrogen
catalog, finish/stop reason Prom, successor_model exposure, and the 11-26
PRD wave. Open bands 474–512 plus today's 513–517 still in flight; local
E2E regression watchdog open.

**Outward (delta since 11-26).** LiteLLM **1.108.20 LTS** (2026-11-27):
non-string Anthropic `tool_call_id` → 400; cancelled Responses streams bill
provider usage; `GET /audit` after team/key updates. Stable GA floor still
**1.111.0**; **1.112.0-rc.1** / **1.113.0-dev.1** remain hold-GA (app
groups, JWT `public_key_url`, Redis cooldowns, Lens, FOCUS 1.5,
priority queues). Portkey Enterprise Gateway **2.34.2** (resync perf);
**2.34.0** `TRUSTED_CUSTOM_HOSTS` SSRF floor still the parity gap. OpenRouter
SDK follow-ups only (`creator_user_id` on `GET /keys` from 11-25 still
unfiled until this run). Ollama **0.40.19** now **stable** (Inkling-2
short-history + MLX Engram). Kong AI GW / vLLM otherwise flat vs prior.

**Inward theme: egress trust + tenancy grouping after exclusivity.**
BYOK exclusivity / required headers / provisional providers / OAuth
`extra_token_params` / `compaction_trigger` already filed. Next failure
modes: frontier custom-host SSRF (MCP guarded, L6 not), app-group shared
budgets, management-key creator filters, and honest LTS/Ollama floors.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 513 | `TRUSTED_CUSTOM_HOSTS` allowlist for frontier custom base URLs | 4 | 2 | Portkey 2.34.0 | MCP already SSRF-safe; L6 must match | Filed [#2529](https://github.com/naveenreddyalka/daari/issues/2529) |
| 514 | App groups with shared budgets and usage | 4 | 2 | LiteLLM 1.113 (#53232) | On-box chargeback across keys/teams | Filed [#2530](https://github.com/naveenreddyalka/daari/issues/2530) |
| 515 | `GET /v1/daari/keys?creator_user_id=` management filter | 3 | 1 | OpenRouter 11-25 | SSO subject already local | Filed [#2531](https://github.com/naveenreddyalka/daari/issues/2531) |
| 516 | Promote LiteLLM LTS floor to 1.108.20 | 2 | 1 | LiteLLM LTS notes | Honest skip-LiteLLM guidance | Filed [#2532](https://github.com/naveenreddyalka/daari/issues/2532) |
| 517 | Ollama 0.40.19 GA floor (Inkling-2 / Engram) | 2 | 1 | Ollama release | Local TTFT honesty on Metal | Filed [#2533](https://github.com/naveenreddyalka/daari/issues/2533) |
| 508–512 | BYOK `is_exclusive`; per-key headers; OAuth `extra_token_params`; provisional providers; `compaction_trigger` | 3–4 | 1–2 | OR / LiteLLM / Portkey | Tenancy + IdP + Codex wire | Open [#2510](https://github.com/naveenreddyalka/daari/issues/2510)–[#2514](https://github.com/naveenreddyalka/daari/issues/2514) |
| 505–507 | Speech `output_delivery`; batches `/results`; evening fence | 2–3 | 2 | OpenRouter TTS/Batches | Local FileStore + hermetic pins | Open [#2470](https://github.com/naveenreddyalka/daari/issues/2470)–[#2472](https://github.com/naveenreddyalka/daari/issues/2472) |
| 499–502 | Tenant-BYOK breaker; `context_management`; compare 1.111.0; overnight fence | 2–4 | 1–2 | LiteLLM / OpenRouter | Credential blast radius + wire-shape | Open [#2463](https://github.com/naveenreddyalka/daari/issues/2463)–[#2466](https://github.com/naveenreddyalka/daari/issues/2466); compare **Shipped** |
| 494–498 | Healthcare catalog; PHI/BAA; `configuration_update`; chat-latest; night fence | 2–4 | 1–2 | OpenAI | Clinical pins + Responses honesty | Open [#2453](https://github.com/naveenreddyalka/daari/issues/2453)–[#2457](https://github.com/naveenreddyalka/daari/issues/2457) |
| 474–493 | Marketplace data-policy; TTS duration; deadlines; Opus/EFS; Neon; fences | 2–4 | 1–2 | OR / LiteLLM / Anthropic | Policy + FinOps | Open bands; many Shipped |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger meters; finish the console | **Inventory + profiles + nested usage + web-ui pagination Shipped** |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **1.112.0-rc.1 / 1.113.0-dev.1** remainder
(control plane, gpt-live-1 WebRTC, priority queues, Lens, FIPS 140-3,
Redis-shared cooldowns, Meta Muse / Live Avatar, JWT `public_key_url`
incremental, **FOCUS 1.5** `ServiceProviderName` — hold GA); OpenRouter
`allow_safety_retention_*` (fold with retention honesty); Anthropic EFS
webhook relay; MCP next **2027-03-30**; Opus 4.8 fast removal **11-30**
(lifecycle shield shipped); Sol promo → baseline on **2026-11-30** (cliff
shipped; docs honesty sibling still open); Astra/Sol for Law + Rosalind
(row 8); semantic-router / Kong / vLLM / A2A / SCIM / Web IQ —
demand-triggered.

Verified fine this run — don't re-audit: Sol/Carbon `effective_to`;
hot-reload; end-user inventory + guardrail profiles; nested multi-agent
usage; web-ui key/team pagination; per-key/team `zero_retention`;
`rate_limited_by` + typed overload envelopes; spend/latency/error alerts;
Hydrogen catalog; per-key-per-model rpm/tpm/rpd/tpd; `prompt_cache_key` /
`prompt_cache_options`; session pin prefix-hash; oauth mint
scope/audience/resource (extra params still open); budget reservation
Grafana + doctor; ZDR retention refuse; Opus 4.8 speed lifecycle shield;
global `server.header_policy` (per-key overlay still open); MCP egress
SSRF (frontier custom-host is the new gap).

---

## Path to enterprise-grade — next 5 milestones

1. **Egress trust + tenancy grouping** — frontier `TRUSTED_CUSTOM_HOSTS`
   (513); app groups shared budgets (514); BYOK `is_exclusive` (508);
   per-key/team required headers (509); tenant-BYOK breaker (499).
2. **Management + IdP honesty** — keys `creator_user_id` filter (515);
   OAuth `extra_token_params` (510); provisional-providers dial (511);
   data-policy floor (474); EFS honesty.
3. **Frontier wire-shape** — `compaction_trigger` chat bridge (512);
   `context_management` (500); speech `output_delivery` (505); batches
   `/results` (506); `configuration_update` / reasoning.exclude /
   previous_response_id refuse.
4. **Billing + compare freshness** — LTS floor 1.108.20 (516); Ollama
   0.40.19 (517); TTS duration; healthcare catalog; Neon / Priority image;
   Sol docs honesty sibling; hold 1.113-dev / FOCUS 1.5 until GA.
5. **Ops + fences + console** — fences through 507 + new wave; tool-fee /
   zdr_retention Prom; then demand-triggered row 8.

---

## Changelog

- **2026-11-27 (LiteLLM 1.108.20 LTS; Ollama 0.40.19 GA; Portkey SSRF)** —
  Outward: LiteLLM 1.108.20 LTS (tool_call_id 400, cancelled Responses
  usage, audit fix); Ollama 0.40.19 stable; Portkey 2.34.2; OR/Kong/vLLM
  flat. Inward: web-ui pagination + zero_retention + overload/
  rate_limited_by + alerts + Hydrogen Shipped. Filed: frontier
  TRUSTED_CUSTOM_HOSTS (513); app groups (514); keys creator_user_id
  (515); LTS 1.108.20 compare (516); Ollama 0.40.19 floor (517).

- **2026-11-26 (LiteLLM 1.113-dev.1; Portkey 2.34.1; BYOK exclusivity)** —
  Filed: BYOK is_exclusive (508); per-key required headers (509);
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
