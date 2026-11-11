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

## Where daari stands (verified in-tree, 2026-11-11 pm)

**Loop velocity.** Overnight merges shipped rows 328 and 330–332
(cost-aware selection #2226, SLO-demotion panel #2227, LTS floor #2228,
OpenRouter Auto compare #2229). Morning fidelity cut filed 365–369.
Open cliffs: 5.2 set (350–354), Kong deep-cut (345–349), 11-10 waves
(355–364), morning 1.109.0 fidelity (365–369).

**Outward.** **Gemini 4 Carbon GA (11-10)** for API + AI Studio — intro
$2/$10 through 11-30, then $4/$20; Argon sibling same ladder; neither id
in `_DEFAULT_MODEL_PRICES`. LiteLLM **v1.109.0 stable** (disk-cache
removed; deployment `rpd`/`tpd`; abort/missing-`finish_reason` streams
fail visibly) + **1.108.5 LTS**; **1.110.0-rc.1** = Rust router + Skills
Hub RC (hold for stable). Ollama **0.40.17-rc0** still rc → floor
**0.40.16**. Flat: Kong 2.3.1 (CVE-only), Portkey v2.33.1, vLLM 0.33.0,
OpenRouter Auto/Auto Code (docs positioned; recipe converted this run).
MCP file-uploads draft → watch.

**Inward theme: route like Auto Code + honor the new frontier cards.**
Coding-router recipe trigger fired (effort lever + cost selection both
shipped) with no tutorial compose. Catalog silent on Gemini 4. Model
rate map has rpm/tpm only — no daily `rpd`/`tpd` to fail over a burned
L6 candidate. Several stream paths still synthesize `stop` when upstream
aborts or omits `finish_reason`.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Filed [#2238](https://github.com/naveenreddyalka/daari/issues/2238) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Filed [#2239](https://github.com/naveenreddyalka/daari/issues/2239) |
| 372 | Per-model daily `rpd`/`tpd` + virtual-model failover on exhaust | 3 | 2 | LiteLLM 1.109.0 deployment daily limits | Burn one L6 daily quota; walk continues on local peers | Filed [#2240](https://github.com/naveenreddyalka/daari/issues/2240) |
| 373 | Streams that `abort` or omit `finish_reason` fail visibly + failover | 4 | 2 | LiteLLM 1.109.0 stream-failure visibility | On-box failover salvages cancelled/truncated turns | Filed [#2241](https://github.com/naveenreddyalka/daari/issues/2241) |
| 374 | Integration fence for the 11-11 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: coding compose, Carbon rates, daily skip, abort | Filed [#2242](https://github.com/naveenreddyalka/daari/issues/2242) |
| 365 | Honest `stop_reason` on `/v1/messages` (capture `pause_turn`/`max_tokens`/`refusal`) | 4 | 2 | LiteLLM 1.109.0 pause_turn + length fixes | One box fronts local + frontier; truncation and pauses surface truthfully | Filed [#2232](https://github.com/naveenreddyalka/daari/issues/2232) |
| 366 | Guardrails scan assistant `tool_calls` arguments (+ opt-in system scan) | 4 | 2 | LiteLLM 1.109.0 hide-secrets surface fix | Secrets scrubbed on-box before any byte leaves | Filed [#2233](https://github.com/naveenreddyalka/daari/issues/2233) |
| 367 | Streamed L0 hits must not drop cached `tool_calls` | 3 | 2 | LiteLLM 1.109.0 streamed-cache-hit fix | The $0 cache tier must be byte-faithful | Filed [#2234](https://github.com/naveenreddyalka/daari/issues/2234) |
| 368 | compare-litellm: 1.109.0 stable floor + 1.108.5 LTS + disk-cache removal positioning | 3 | 1 | LiteLLM release notes | They removed disk caching; daari's L1 **is** diskcache | Filed [#2235](https://github.com/naveenreddyalka/daari/issues/2235) |
| 369 | Integration fence for the 11-10/11-11 overnight wave | 2 | 2 | — (testability) | Hermetic proof: cost-aware selection; SLO panel | Filed [#2236](https://github.com/naveenreddyalka/daari/issues/2236) |
| 360 | Expand OpenAI residency 1.10× + docs to CA/SG/KR/GB/AE | 3 | 1 | OpenAI regional hosts + invoice uplift | Same-box ledger matches regional invoice | Filed [#2220](https://github.com/naveenreddyalka/daari/issues/2220) |
| 361 | Opt-in Anthropic `auto_caching` via top-level `cache_control` | 3 | 2 | Portkey 2.33.0 auto_caching | Claude automatic cache without a SaaS config plane | Filed [#2221](https://github.com/naveenreddyalka/daari/issues/2221) |
| 362 | Opt-in failover on any HTTP 5xx incl. 501/522 | 3 | 2 | Kong 2.3.0 `http_5xx` failover_criteria | Local/frontier 5xx fail over on-box; no Cedar dep | Filed [#2222](https://github.com/naveenreddyalka/daari/issues/2222) |
| 363 | Require Fable/Mythos 5.2-compatible advisor model | 3 | 2 | Anthropic 11-09 advisor pairing gate | Fail-fast before the cloud 400 | Filed [#2223](https://github.com/naveenreddyalka/daari/issues/2223) |
| 364 | Integration fence for the 11-10 evening wave | 2 | 2 | — (testability) | Hermetic proof: residency, auto_caching, 5xx, advisor | Filed [#2224](https://github.com/naveenreddyalka/daari/issues/2224) |
| 355 | Round-trip OpenAI encrypted reasoning on `/v1/messages` across turns | 4 | 2 | LiteLLM 1.108.4 LTS reasoning fix | Reasoning fidelity survives any executor | Filed [#2214](https://github.com/naveenreddyalka/daari/issues/2214) |
| 356 | Honor `truncation` auto/disabled on `/v1/responses` | 3 | 2 | Ollama 0.40.16 honors it; OpenAI semantics | Compact on-box; payload never leaves | Filed [#2215](https://github.com/naveenreddyalka/daari/issues/2215) |
| 357 | Per-team frontier credential binding (team BYOK) | 4 | 3 | LiteLLM team BYOK (1.108.4 precedence fix) | Each team's L6 bills to their invoice; local stays $0 | Filed [#2216](https://github.com/naveenreddyalka/daari/issues/2216) |
| 358 | Ripple Preview L4/L5 agentic-coding recipe (Ollama ≥ 0.40.16) | 3 | 1 | Ollama 0.40.16 `ripple-preview` | $0 on-box coding agent tier + VRAM guidance | Filed [#2217](https://github.com/naveenreddyalka/daari/issues/2217) |
| 359 | Integration fence for the 11-09/11-10 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny/PATCH, residency, effort, VK grace | Filed [#2218](https://github.com/naveenreddyalka/daari/issues/2218) |
| 350 | Ship Claude Fable 5.2 / Mythos 5.2 catalog rates + caps + fast mode | 4 | 2 | Anthropic Platform 11-09 list prices | Honest on-box ledger vs invoice | Filed [#2204](https://github.com/naveenreddyalka/daari/issues/2204) |
| 351 | Drop Fable/Mythos 5.2 thinking when failover switches model | 4 | 2 | Anthropic mid-conversation drop (11-09) | On-box switch owns the strip | Filed [#2205](https://github.com/naveenreddyalka/daari/issues/2205) |
| 352 | Require `computer_toolset_20260801` on Fable/Mythos 5.2 | 3 | 2 | Anthropic 11-09 toolset gate | Gateway rewrite/fail-fast before the 400 | Filed [#2206](https://github.com/naveenreddyalka/daari/issues/2206) |
| 353 | Config ownership + PATCH for `routing.baggage_to_tags` | 3 | 1 | LiteLLM baggage→tags / Portkey Complete Logs | Hot-edit mesh-identity dial | Filed [#2207](https://github.com/naveenreddyalka/daari/issues/2207) |
| 354 | Integration fence for the 11-09 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: baggage tags, service-tier Grafana, 5.2 smoke | Filed [#2208](https://github.com/naveenreddyalka/daari/issues/2208) |
| 345 | Default `drop_block` thinking binding on preserved-thinking Claude | 4 | 2 | Kong 2.3.0 default drop_block | daari mutates the prefix so daari owns the binding | Filed [#2196](https://github.com/naveenreddyalka/daari/issues/2196) |
| 346 | Bill server-side tools beyond web search + `tool_usage` breakdown | 4 | 2 | Kong 2.3.0 `usage.tool_cost`/`tool_usage` | On-box ledger reconciles with provider invoice | Filed [#2197](https://github.com/naveenreddyalka/daari/issues/2197) |
| 347 | Opt-in in-flight budget reservation (pre-charge, settle actual) | 4 | 3 | Kong 2.3.0 rate-limit cost pre-charge | Parallel bursts can't blow the window | Filed [#2198](https://github.com/naveenreddyalka/daari/issues/2198) |
| 348 | Opt-in cardinality-capped per-key label on Prometheus series | 3 | 2 | Kong 2.3.0 `enable_credential_attribute` | Per-key FinOps from the same-box scrape | Filed [#2199](https://github.com/naveenreddyalka/daari/issues/2199) |
| 349 | Integration fence for the 11-08/11-09 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny, revoke-subject, AutoTrust, MiMo | Filed [#2200](https://github.com/naveenreddyalka/daari/issues/2200) |
| 340–344 | Credential patterns; log_blocked ownership; effort=none; cost Prom; fence | 2–3 | 1–2 | LiteLLM 1.110-dev / Kong | On-box scrub + FinOps scrape | Filed [#2186](https://github.com/naveenreddyalka/daari/issues/2186)–[#2190](https://github.com/naveenreddyalka/daari/issues/2190) |
| 335–339 | MCP egress fidelity + SSE; cost split; blocked-content log; fence | 2–4 | 2 | LiteLLM 1.108.3 / Kong 2.3.0 | Byte-faithful local tools + FinOps truth | Filed [#2180](https://github.com/naveenreddyalka/daari/issues/2180)–[#2184](https://github.com/naveenreddyalka/daari/issues/2184) |
| 330–332 | SLO-demotion Grafana; compare LTS floor; OpenRouter Auto compare | 2–3 | 1 | OpenRouter / LiteLLM release notes | Same-box scrape + honest compare floors | Shipped (#2227–#2229) |
| 333–334 | OTel request-tags ownership PATCH; 11-07 afternoon fence | 2–3 | 1–2 | Portkey / LiteLLM | Hot-edit tag export on operator-owned OTel | Filed [#2172](https://github.com/naveenreddyalka/daari/issues/2172), [#2173](https://github.com/naveenreddyalka/daari/issues/2173) |
| 326–328 | Effort lever; VK grace across PG blips; cost-aware selection | 3–4 | 2 | OpenRouter Auto / LiteLLM 1.108.2 | Effort + $0-first arithmetic on-box | Shipped (#2212, #2213, #2226) |
| 321–324 | Service-tier Grafana; baggage→tags; allowed_ips console; AU/IN/JP residency | 2–3 | 1–2 | OpenAI / LiteLLM / Anthropic | Governance + residency dials | Shipped (#2202, #2203, #2210, #2211) |
| 316–319 | IP allowlist CIDR; revoke-subject; AutoTrust; MiMo recipe | 3–4 | 1–2 | Anthropic Console / Ollama 0.40.15 | Blast-radius + local catalog | Shipped (#2192–#2195) |
| 279, 285, 274 | Offline Prom + doctor; failover Grafana panels | 2 | 1 | — (ops honesty) | Prove the air gap / failover pressure | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072), [#2079](https://github.com/naveenreddyalka/daari/issues/2079), [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **MCP file-uploads draft extension**
(`io.modelcontextprotocol/files`, experimental, no reference impl — file
when stable ~end of year); LiteLLM 1.109.0 remainder (K8s headless-pod
discovery; size-capped spend-log retention analog; non-chat deployment
filter) — convert on buyer ask; **`pricing_provider` already shipped
(#2005)** — drop from watch; **1.110.0-rc.1** (Rust-only router, Agent
Skills Hub, Responses SSE without `[DONE]`, unmanaged response-id reject)
→ hold for stable; Ollama 0.40.17-rc0 (MLX concurrent gen — hold for GA);
Fable/Mythos 5.2 30-day retention / ZDR carve-out honesty (after 350);
Kong Cedar `access-policy-engine` + CEL tool ACL + Token Vault (new dep —
human); Grafana panels for input/output cost USD (after 343); LiteLLM
`1.110.0-dev` remainder beyond 340/342; Portkey MCP access policies
(Prisma AIRS-only); Bedrock metadata map; OpenAI Live `/v1/live/sessions`
+ Azure PTU + M365 Copilot; AutoTrust beyond Apple silicon; `gpt-6-cyber`
(Daybreak); gpt-image-2.6; Agents API `auto_review`; Anthropic text
watermark; minute-grain spend; fleet Redis EWMA; MCP SEP-3398; OpenAI org
external key management; Anthropic Compliance API; `between_tools`
Sonnet-5.5-only; `gpt-6-rosalind`; Claude Code `groups` / `guardrail_trace`;
Claude Tag beta; OpenRouter private-provider CRUD; LiteLLM Admin Chat UI /
Lens; llama.cpp `/v1/realtime` + `POST /tts`; Portkey claim JWT / WIF;
OpenAI `/agents/automations`; Prisma AIRS Agent Identity; Claude-on-GCP
IAM (new dep); Anthropic hosted skills; Open Responses WS; Anthropic OTel
export beta; Prom exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG; SCIM +
multi-issuer SSO; Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe;
certifi emSign; Ollama d1 Linux/Windows GA; local message-thread analogue;
A2A 1.1 RC (wait for two-SDK gate).

Verified fine this run — don't re-audit: mid-stream fallback continuation,
session repin after failover, `prompt_cache_retention`, `redacted_thinking`,
stream resume, stream idle timeout, frontier `stream_incomplete` on raised
relay errors (abort / missing-finish_reason still synthesize `stop` —
row 373), `pricing_provider` catalog alias (#2005), request_log **days**
retention (#772; byte-cap still watch).

---

## Path to enterprise-grade — next 5 milestones

1. **Agent-loop fidelity on every executor** — abort/missing-finish_reason
   (373); honest `stop_reason` / `pause_turn` (365); streamed cache-hit
   tool_calls (367); 5.2 catalog + thinking strip + advisor + toolset
   (350–352, 363); encrypted-reasoning (355); drop_block (345);
   `truncation` (356); MCP egress (335–336).
2. **Route like Auto Code on-box** — coding-router recipe (370); Carbon /
   Argon catalog (371); cost-aware selection (328 shipped); Ripple (358);
   effort lever (326 shipped); auto_caching (361); any-5xx failover (362).
3. **FinOps + tenancy that reconcile** — per-model daily rpd/tpd (372);
   residency uplift (360); team BYOK (357); server-side tool billing (346);
   budget reservation (347); cost split (337) + Prom (343); per-key label
   (348).
4. **Contain the leaked key** — tool_call argument scan (366); credential
   patterns (340); blocked-content forensics (338) + ownership (341).
5. **Survive the control-plane blip + honest compare** — offline Prom
   (279) + doctor (285); hot-reload (6); OTel tags PATCH (333); failover
   panels (274); LiteLLM 1.109.0 compare + disk-cache positioning (368);
   fences through 374; then rows 62–67.

---

## Changelog

- **2026-11-11 pm (coding-router + Gemini 4 Carbon cliff)** — Converted
  fired coding-router recipe watch (row 370). Outward: **Gemini 4 Carbon
  GA** (intro $2/$10 → $4/$20 Dec 1; Argon same ladder; zero hits in-tree);
  LiteLLM 1.109.0 remainder mined for deployment daily `rpd`/`tpd` (372)
  and abort/missing-`finish_reason` stream honesty (373); 1.110.0-rc.1 +
  Ollama 0.40.17-rc0 remain watch. Filed afternoon fence (374). Dropped
  `pricing_provider` from watch (shipped #2005). Verified: stream idle +
  raised-relay `stream_incomplete` exist; synthesize-`stop` paths remain.

- **2026-11-11 (LiteLLM 1.109.0 fidelity cut)** — Marked 328, 330–332
  Shipped. Filed honest `stop_reason` (365), tool_calls guardrail scan
  (366), streamed L0 tool_calls (367), compare 1.109.0 + disk-cache
  positioning (368), overnight fence (369). Coding-router trigger noted
  for next run (converted above).

- **2026-11-10 pm → 11-08** — Condensed: residency / auto_caching / 5xx /
  advisor (360–364); reasoning fidelity + team BYOK + truncation + Ripple
  (355–359); Fable/Mythos 5.2 cliff (350–354); Kong 2.3.0 deep cut
  (345–349); privacy dials + FinOps scrape (340–344); MCP egress + Kong
  cost split (335–339).

- **2026-11-07 → 10-28** — Condensed: Auto-Router converts + PG-blip grace;
  observe/compare tail; leaked-key blast radius + Ollama 0.40.15; TTFT/SLO
  observe; governance console / Codex PAT; through Apache 2.0 and this
  PRD's creation. Issue #2141 still needs human close.
