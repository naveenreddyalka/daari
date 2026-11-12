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

## Where daari stands (verified in-tree, 2026-11-12)

**Loop velocity.** Overnight merges shipped rows 333, 335–338, 340
(OTel-tags ownership #2230, MCP egress fidelity #2244/#2245, cost split
#2246, block forensics #2247, credential patterns #2248). The 11-11 pm
Actions PRD PR died on the pin test and was drained as a no-op — its
rows 370–374 (issues #2238–#2242) are restored below.

**Outward.** **LiteLLM emergency security night (11-12):** one fix
(litellm#51254 — client bodies could override admin credential fields
and smuggle `os.environ/` secret refs) backported to **all four live
branches** (v1.109.1 GA, v1.108.6 LTS, v1.106.9, v1.110.0-rc.2). daari
is immune by design — allowlist payloads, `secret://` resolves from
Settings only (row 378 proves + fences it). 1.108.6 also carried
mineable LTS fixes: `allowed_tools` tool_choice both layouts (→ 377),
Gemini image-edit token billing (→ 375), idempotent spend resets +
comma scope grants (verified N/A below). MCP blog 11-11:
release-cadence post (governance only). Anthropic 11-12: **self-hosted
Claude Managed Agents** (watch — daari can be its chosen provider
endpoint). Flat: Kong 2.3.1, Portkey v2.33.1, vLLM 0.33.0, OpenRouter
(10-29), Ollama 0.40.17-rc0 (floor 0.40.16), OpenAI (11-05).

**Inward theme: billing truth on the modality surfaces.** Every
`/v1/images/*` call and the frontier ASR leg record `reported_cost=0.0`
— real frontier dollars invisible to budgets, ledger, and cost headers
(a budget-capped key spends unbounded through images). The images
default model is 2024-era `dall-e-3`; gpt-image-2.6 (11-04, token-
billed) is absent. `tool_choice: allowed_tools` is silently dropped on
the Anthropic path — a tool-governance bypass.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 375 | Bill frontier image generations/edits from upstream `usage`; gpt-image-2.6 catalog rates | 4 | 2 | OpenAI token-billed images; LiteLLM 1.108.6 Gemini image-edit billing | Image spend lands in the same-box ledger/budgets that meter chat | Filed [#2249](https://github.com/naveenreddyalka/daari/issues/2249) |
| 376 | Bill the frontier ASR leg honestly (duration/token rates); local stays $0 | 3 | 2 | OpenAI per-minute/token ASR billing | The fallback that costs money is the leg the ledger must meter | Filed [#2250](https://github.com/naveenreddyalka/daari/issues/2250) |
| 377 | Honor `tool_choice: allowed_tools` (nested + flat) across Anthropic + local backends | 3 | 2 | LiteLLM 1.108.6 LTS (#49043/#50467) | One tool-governance contract at the edge for every executor | Filed [#2251](https://github.com/naveenreddyalka/daari/issues/2251) |
| 378 | Prove + fence client credential-field hygiene (immune to the litellm#51254 class); floors 1.109.1/1.108.6 | 3 | 1 | LiteLLM (after its emergency patch) | Allowlist payloads never needed the patch — argue it with a test | Filed [#2252](https://github.com/naveenreddyalka/daari/issues/2252) |
| 379 | Integration fence for the 11-11/11-12 overnight wave | 2 | 2 | — (testability) | Hermetic proof: MCP egress fidelity, cost split, forensics, patterns | Filed [#2253](https://github.com/naveenreddyalka/daari/issues/2253) |
| 370 | Coding-router recipe (virtual_models + code signals + cost/SLO/effort) | 4 | 2 | OpenRouter Auto Code (hosted) | $0 local-first coding compose on-box; marketplace stays optional L6 | Filed [#2238](https://github.com/naveenreddyalka/daari/issues/2238) |
| 371 | Ship Gemini 4 Carbon + Argon catalog rates + capabilities | 4 | 2 | Google AI Studio / LiteLLM day-0 | Honest on-box ledger vs Gemini invoice incl. Dec 1 step-up | Filed [#2239](https://github.com/naveenreddyalka/daari/issues/2239) |
| 372 | Per-model daily `rpd`/`tpd` + virtual-model failover on exhaust | 3 | 2 | LiteLLM 1.109.0 deployment daily limits | Burn one L6 daily quota; walk continues on local peers | Filed [#2240](https://github.com/naveenreddyalka/daari/issues/2240) |
| 373 | Streams that `abort` or omit `finish_reason` fail visibly + failover | 4 | 2 | LiteLLM 1.109.0 stream-failure visibility | On-box failover salvages cancelled/truncated turns | Filed [#2241](https://github.com/naveenreddyalka/daari/issues/2241) |
| 374 | Integration fence for the 11-11 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: coding compose, Carbon rates, daily skip, abort | Filed [#2242](https://github.com/naveenreddyalka/daari/issues/2242) |
| 365 | Honest `stop_reason` on `/v1/messages` (capture `pause_turn`/`max_tokens`/`refusal`) | 4 | 2 | LiteLLM 1.109.0 pause_turn + length fixes | One box fronts local + frontier; truncation and pauses surface truthfully on one contract | Filed [#2232](https://github.com/naveenreddyalka/daari/issues/2232) |
| 366 | Guardrails scan assistant `tool_calls` arguments (+ opt-in system scan) | 4 | 2 | LiteLLM 1.109.0 hide-secrets surface fix | Secrets scrubbed on-box before any byte leaves; #2186 patterns need the surface | Filed [#2233](https://github.com/naveenreddyalka/daari/issues/2233) |
| 367 | Streamed L0 hits must not drop cached `tool_calls` | 3 | 2 | LiteLLM 1.109.0 streamed-cache-hit fix | The $0 cache tier must be byte-faithful or agent loops can't trust it | Filed [#2234](https://github.com/naveenreddyalka/daari/issues/2234) |
| 368 | compare-litellm: 1.109.0 stable floor + 1.108.5 LTS + disk-cache removal positioning | 3 | 1 | LiteLLM release notes | They removed disk caching; daari's L1 **is** a local diskcache — hard differentiator | Filed [#2235](https://github.com/naveenreddyalka/daari/issues/2235) |
| 369 | Integration fence for the 11-10/11-11 overnight wave | 2 | 2 | — (testability) | Hermetic proof: cost-aware selection prefers $0 local; SLO panel pinned | Filed [#2236](https://github.com/naveenreddyalka/daari/issues/2236) |
| 360 | Expand OpenAI residency 1.10× + docs to CA/SG/KR/GB/AE | 3 | 1 | OpenAI regional hosts + invoice uplift | Same-box ledger matches regional invoice; storage-vs-processing honesty next to the pin | Filed [#2220](https://github.com/naveenreddyalka/daari/issues/2220) |
| 361 | Opt-in Anthropic `auto_caching` via top-level `cache_control` | 3 | 2 | Portkey 2.33.0 auto_caching | Agent loops get Claude automatic cache without a SaaS config plane | Filed [#2221](https://github.com/naveenreddyalka/daari/issues/2221) |
| 362 | Opt-in failover on any HTTP 5xx incl. 501/522 | 3 | 2 | Kong 2.3.0 `http_5xx` failover_criteria | Local/frontier 5xx fail over on-box; no Cedar dep | Filed [#2222](https://github.com/naveenreddyalka/daari/issues/2222) |
| 363 | Require Fable/Mythos 5.2-compatible advisor model | 3 | 2 | Anthropic 11-09 advisor pairing gate | Fail-fast before the cloud 400; agent loop stays on-box | Filed [#2223](https://github.com/naveenreddyalka/daari/issues/2223) |
| 364 | Integration fence for the 11-10 evening wave | 2 | 2 | — (testability) | Hermetic proof: residency pins, auto_caching, 5xx failover, advisor gate | Filed [#2224](https://github.com/naveenreddyalka/daari/issues/2224) |
| 355 | Round-trip OpenAI encrypted reasoning on `/v1/messages` across turns | 4 | 2 | LiteLLM 1.108.4 LTS reasoning fix | One box fronts both vendors; reasoning fidelity survives any executor, no SaaS middle layer | Filed [#2214](https://github.com/naveenreddyalka/daari/issues/2214) |
| 356 | Honor `truncation` auto/disabled on `/v1/responses` | 3 | 2 | Ollama 0.40.16 honors it; OpenAI semantics | Local tiers hit context walls first; compact on-box, payload never leaves | Filed [#2215](https://github.com/naveenreddyalka/daari/issues/2215) |
| 357 | Per-team frontier credential binding (team BYOK) | 4 | 3 | LiteLLM team BYOK (1.108.4 precedence fix) | Each team's L6 bills to their own invoice; shared local tiers stay $0 | Filed [#2216](https://github.com/naveenreddyalka/daari/issues/2216) |
| 358 | Ripple Preview L4/L5 agentic-coding recipe (Ollama ≥ 0.40.16) | 3 | 1 | Ollama 0.40.16 `ripple-preview` | $0 on-box coding agent tier with honest 65B-dense VRAM guidance | Filed [#2217](https://github.com/naveenreddyalka/daari/issues/2217) |
| 359 | Integration fence for the 11-09/11-10 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny/PATCH, residency 1.10×, effort lever, VK grace | Filed [#2218](https://github.com/naveenreddyalka/daari/issues/2218) |
| 350 | Ship Claude Fable 5.2 / Mythos 5.2 catalog rates + caps + fast mode | 4 | 2 | Anthropic Platform 11-09 list prices | Honest on-box ledger vs invoice; local tiers stay $0 | Filed [#2204](https://github.com/naveenreddyalka/daari/issues/2204) |
| 351 | Drop Fable/Mythos 5.2 thinking when failover switches to another model | 4 | 2 | Anthropic mid-conversation drop (11-09) | On-box switch owns the strip; agent loop survives without a cloud round-trip | Filed [#2205](https://github.com/naveenreddyalka/daari/issues/2205) |
| 352 | Require `computer_toolset_20260801` on Fable/Mythos 5.2 (reject `computer_20251124`) | 3 | 2 | Anthropic 11-09 toolset gate | Gateway rewrite/fail-fast before the 400; Bedrock exception kept | Filed [#2206](https://github.com/naveenreddyalka/daari/issues/2206) |
| 353 | Config ownership + PATCH for `routing.baggage_to_tags` | 3 | 1 | LiteLLM baggage→tags / Portkey Complete Logs | Hot-edit mesh-identity dial on the same-box console | Filed [#2207](https://github.com/naveenreddyalka/daari/issues/2207) |
| 354 | Integration fence for the 11-09 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: baggage tags, service-tier Grafana, 5.2 catalog smoke | Filed [#2208](https://github.com/naveenreddyalka/daari/issues/2208) |
| 345 | Default `drop_block` thinking binding on preserved-thinking Claude (replay-after-prefix-change 400s) | 4 | 2 | Kong 2.3.0 default drop_block | daari mutates the prefix (compress/compact) so daari owns the binding fix | Filed [#2196](https://github.com/naveenreddyalka/daari/issues/2196) |
| 346 | Bill server-side tools beyond web search + per-tool `tool_usage` breakdown | 4 | 2 | Kong 2.3.0 `usage.tool_cost`/`tool_usage` | On-box ledger reconciles with the provider invoice, no SaaS analytics | Filed [#2197](https://github.com/naveenreddyalka/daari/issues/2197) |
| 347 | Opt-in in-flight budget reservation (pre-charge estimate, settle actual) | 4 | 3 | Kong 2.3.0 rate-limit cost pre-charge | Ledger + admission + pricing on one box; parallel bursts can't blow the window | Filed [#2198](https://github.com/naveenreddyalka/daari/issues/2198) |
| 348 | Opt-in cardinality-capped per-key label on Prometheus series | 3 | 2 | Kong 2.3.0 `enable_credential_attribute` + limit | Per-key FinOps from the same-box scrape; `team_metrics` pattern proven | Filed [#2199](https://github.com/naveenreddyalka/daari/issues/2199) |
| 349 | Integration fence for the 11-08/11-09 overnight wave | 2 | 2 | — (testability) | Hermetic proof: IP deny, revoke-subject, AutoTrust, MiMo | Filed [#2200](https://github.com/naveenreddyalka/daari/issues/2200) |
| 333, 335–338, 340 | OTel-tags ownership; MCP egress fidelity + SSE framing; cost input/output split; block forensics; credential patterns | 3–4 | 1–2 | Kong 2.3.0 / LiteLLM 1.108.3–1.110-dev | Byte-faithful egress + on-box forensics and FinOps | Shipped (#2230, #2244–#2248) |
| 341 | Config ownership + PATCH for `guardrails.log_blocked_content` | 3 | 1 | Kong / LiteLLM control-plane toggles | Hot-edit forensics dial on the operator console | Filed [#2187](https://github.com/naveenreddyalka/daari/issues/2187) |
| 342 | `reasoning_effort`/`output_config.effort` `none` disables Claude 5.5 adaptive thinking | 3 | 2 | LiteLLM 1.110.0-dev.2 Anthropic fix | Zero-thinking means zero thinking tokens on L6 | Filed [#2188](https://github.com/naveenreddyalka/daari/issues/2188) |
| 343 | Prometheus + stats counters for input/output cost USD | 3 | 2 | Kong 2.3.0 analytics / LiteLLM Admin | Same-box scrape once the cost split lands | Filed [#2189](https://github.com/naveenreddyalka/daari/issues/2189) |
| 344 | Integration fence for the 11-08 morning MCP/Kong wave | 2 | 2 | — (testability) | Hermetic proof: MCP fidelity, cost split, blocked content | Filed [#2190](https://github.com/naveenreddyalka/daari/issues/2190) |
| 339 | Integration fence for the 11-07/11-08 overnight wave | 2 | 2 | — (testability) | Hermetic proof: SLO PATCH/UI, threads, UA spans, IP omit | Filed [#2184](https://github.com/naveenreddyalka/daari/issues/2184) |
| 330–332 | SLO-demotion Grafana; compare LTS floor; OpenRouter Auto compare | 2–3 | 1 | OpenRouter / LiteLLM release notes | Same-box scrape + honest compare floors | Shipped (#2227–#2229) |
| 334 | Integration fence for the 11-07 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: SLO demotion Prom + OTel request tags | Filed [#2173](https://github.com/naveenreddyalka/daari/issues/2173) |
| 326–328 | `reasoning_effort` signal lever; VK grace across PG blips; cost-aware selection | 3–4 | 2 | OpenRouter Auto / LiteLLM 1.108.2 | Effort + $0-first arithmetic on-box; serve through control-plane restarts | Shipped (#2212, #2213, #2226) |
| 329 | Integration fence for the 11-06/11-07 overnight wave | 2 | 2 | — (testability) | Hermetic proof: Codex PAT, priority Prom, tier inventory | Filed [#2165](https://github.com/naveenreddyalka/daari/issues/2165) |
| 321–324 | Service-tier Grafana; baggage→tags; allowed_ips console; AU/IN/JP residency 1.10× | 2–3 | 1–2 | OpenAI / LiteLLM / Anthropic Console | Governance + residency dials on the same-box console | Shipped (#2202, #2203, #2210, #2211) |
| 325 | Integration fence for the 11-06 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: refusals + service-tier metrics | Filed [#2156](https://github.com/naveenreddyalka/daari/issues/2156) |
| 316–319 | IP allowlist CIDR; revoke-subject kill switch; AutoTrust family; MiMo recipe | 3–4 | 1–2 | Anthropic Console / Ollama 0.40.15 | Blast-radius + local catalog on the same-box console | Shipped (#2192–#2195) |
| 320 | Integration fence for the 11-05/11-06 overnight wave | 2 | 2 | — (testability) | Hermetic proof: temp omit, rate kinds, show limits, rotation | Filed [#2148](https://github.com/naveenreddyalka/daari/issues/2148) |
| 309, 311–314 | SLO PATCH + console; message-thread Prom; UA spans; audit IP omit | 3 | 1–2 | LiteLLM / Portkey / Anthropic / OpenRouter | Governance + privacy dials on the same-box console | Shipped (#2175–#2179) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 307, 308 | SLO demotion Prom/stats; opt-in request tags on OTel GenAI spans | 3 | 1 | OpenRouter / Portkey Complete Logs | Operator-owned traces next to local-tier cost attrs | Shipped (#2166, #2168) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: prior overnight dials | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 299, 301–304, 306 | Refusal parts; service-tier Prom + console; Codex PAT L6; priority Prom; 1.108.0 LTS floor | 2–3 | 1–2 | Ollama / OpenAI / Portkey / LiteLLM | Governance + honesty on the same-box scrape and console | Shipped (#2150–#2151, #2158–#2161) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 294, 296–298 | Rate-limit kind split; temperature omit; batches rotation; `/api/show` limits | 3–4 | 1–2 | LiteLLM / Ollama 0.40.14 | Byte-equivalence + signed push channels | Shipped (#2139–#2140, #2142–#2143) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 281–293 | LTS compare; offline PATCH; batch webhook; tags; OTel cost; latency SLO; vLLM notes; MCP oauth; threads; TPD UI; selection Grafana | 2–4 | 1–3 | LiteLLM / Portkey / OpenRouter / Anthropic | Operator-owned traces, honest tiers, same-box console | Shipped (#2116–#2121, #2128–#2132) |
| 295 | Integration fence for the 11-02 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: TPD + OpenRouter compare pin | Filed [#2097](https://github.com/naveenreddyalka/daari/issues/2097) |
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
| 279 | Prometheus counter for offline-mode refused egress | 2 | 1 | — (ops honesty) | Prove the air gap held from the scrape | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072) |
| 285 | Doctor tip: offline_mode on + live frontier L6 creds | 2 | 1 | — (ops honesty) | Same-box warning before the 403 storm | Filed [#2079](https://github.com/naveenreddyalka/daari/issues/2079) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): **Anthropic self-hosted Claude Managed
Agents (11-12)** — the operator picks the model provider; a recipe
pointing it at daari's Anthropic facade is the convert when a buyer
asks; **MCP file-uploads draft extension** (`io.modelcontextprotocol/files`,
`x-mcp-file` schema marker, blog 11-10 — experimental repo, no reference
impl; file ingress/egress conformance when it stabilizes ~end of year;
blog 11-11 = release-cadence governance, no spec delta);
LiteLLM 1.109.0 remainder (K8s headless-pod discovery for local pools;
`pricing_provider` shadow-pricing for savings honesty; size-capped
request-log retention analog of `maximum_spend_logs_size`; non-chat
deployment filter) — convert on buyer ask; 1.110.0-rc.2 = fixes + the
security backport (hold for stable); Opus 4.8 fast-mode removal 11-30
(warn when `speed:"fast"` targets it — fold into lifecycle warnings on
buyer ask); Ollama 0.40.17-rc0 (MLX concurrent gen — hold for GA);
Fable/Mythos 5.2 30-day retention / ZDR carve-out honesty (after 350);
Kong 2.3.0 Cedar `access-policy-engine` + CEL tool ACL + Token Vault
(expression engine = new dep — human sign-off); Grafana panels for
input/output cost USD (after 343); LiteLLM `1.110.0-dev` remainder
beyond 340/342 (provider-reported `usage.cost`, tenant session affinity,
Lens-split Helm, prompt-storage off, deployment weights, Responses SSE
framing — hold for stable); Portkey MCP
access policies (Prisma AIRS-only); Portkey OTel workspace name; Bedrock
metadata map; LiteLLM OpenAI Live `/v1/live/sessions` + Azure PTU + M365
Copilot + `gpt-live-1` SIP (Realtime/WS); AutoTrust beyond Apple silicon;
`gpt-6-cyber` (Daybreak); Agents API
`auto_review`; Anthropic text watermark (metric-only); minute-grain spend;
fleet Redis EWMA; MCP SEP-3398 (~March 2027); OpenAI org external key
management; Anthropic Compliance API; `between_tools` Sonnet-5.5-only;
`gpt-6-rosalind`; Claude Code `groups` / `guardrail_trace`; OpenRouter
private-provider CRUD; LiteLLM Admin Chat UI / Lens; llama.cpp
`/v1/realtime` + `POST /tts`; Portkey claim JWT / WIF; OpenAI
`/agents/automations`; Prisma AIRS Agent Identity; Claude-on-GCP IAM
(new dep — human); Anthropic hosted skills; Claude Tag beta; Open
Responses WS; Anthropic OTel export beta; Prom exemplars +
`gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer SSO; Kong
Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign;
Ollama d1 Linux/Windows GA; local message-thread analogue (only after
explicit agent-loop ask); A2A 1.1 RC (wait for two-SDK gate).

Verified fine this run (vs LiteLLM 1.108.6/1.109.1) — don't re-audit:
client bodies cannot override credentials or smuggle secret refs —
`openai_payload` is an explicit allowlist (sampling.py ~L689),
`secret://` resolves from Settings only (boot/refresh + doctor), and
the admin config PATCH (openai.py ~L2881) is a validated whitelist with
no credential fields (row 378 fences this); budget window resets are
epoch-derived from the ledger, so their idempotent-resets fix (#50298)
is N/A; MCP egress OAuth never gates on the granted scope string, so
comma-separated grant parsing (#50717) is N/A; TTS targets are local
(Phonon), so $0 TTS metering is honest — the ASR gap (row 376) is the
frontier leg only. Still parity: mid-stream fallback continuation,
session repin, `prompt_cache_retention`, `redacted_thinking`.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing truth everywhere money moves** — image generations/edits
   billed from upstream usage (375); frontier ASR leg (376); Gemini 4
   Carbon/Argon rates (371); 5.2 catalog + fast mode (350); server-side
   tool billing (346); in-flight budget reservation (347); Prom/stats
   for the cost split (343); per-key metric label (348); daily
   `rpd`/`tpd` (372); CA/SG/KR/GB/AE residency uplift (360); per-team
   frontier BYOK (357).
2. **Agent-loop fidelity on every executor** — honest `stop_reason`
   incl. `pause_turn` (365); abort/missing-`finish_reason` honesty
   (373); streamed cache-hit tool_calls (367); `allowed_tools` honored
   (377); thinking strip on model switch (351); advisor pairing (363);
   encrypted-reasoning on Messages (355); `computer_toolset_20260801`
   (352); drop_block (345); `truncation` (356).
3. **Contain the leaked key, prove the hygiene** — credential-field
   hygiene fence (378); scan tool_call arguments + opt-in system scan
   (366); forensics ownership (341).
4. **Route like the new Auto Router** — coding-router recipe (370);
   Claude `effort=none` (342); auto_caching dial (361); any-5xx
   failover (362); Ripple coding tier (358); baggage PATCH (353).
5. **Survive the control-plane blip + honest compare** — offline Prom
   (279) + doctor (285); hot-reload (6); failover panels (274); LiteLLM
   1.109.1/1.108.6 compare + disk-cache positioning (368 + 378); fences
   (300, 305, 310, 315, 320, 325, 329, 334, 339, 344, 349, 354, 359,
   364, 369, 374, 379); then rows 62–67.

---

## Changelog

- **2026-11-12 (billing truth on modality surfaces; LiteLLM security
  night)** — Marked rows 333, 335–338, 340 Shipped (#2230, #2244–#2248
  overnight). Drained the dead 11-11 pm Actions PRD PR (pin-test
  failure) as a no-op and restored its rows 370–374 + changelog here.
  Outward: **litellm#51254 security fix backported to all four live
  branches** (1.109.1 GA / 1.108.6 LTS / 1.106.9 / 1.110.0-rc.2) —
  daari immune by design, converted as prove-and-fence row 378; 1.108.6
  LTS mining → `allowed_tools` (377) and image-billing precedent (375);
  Anthropic self-hosted Managed Agents + MCP release-cadence post →
  watch. Converted inward: frontier images billed $0 with fake token
  counts + stale dall-e-3 default (375), frontier ASR leg billed $0
  (376), `allowed_tools` dropped on Anthropic path (377), overnight
  fence (379). Verified N/A: idempotent spend resets, comma scope
  grants, local-TTS $0 metering.

- **2026-11-11 pm (coding-router recipe, Gemini 4 Carbon, stream
  honesty — restored from the drained Actions PR)** — Filed
  coding-router compose (370), Gemini 4 Carbon/Argon rates incl. the
  Dec 1 step-up (371), per-model daily `rpd`/`tpd` + failover (372),
  abort/missing-`finish_reason` stream honesty (373), afternoon fence
  (374). Gemini 4 Carbon GA'd 11-10 at intro $2/$10 through 11-30.

- **2026-11-11 (LiteLLM 1.109.0 fidelity cut)** — Marked rows 328,
  330–332 Shipped (cost-aware selection, SLO panel, LTS floor,
  OpenRouter compare — all overnight). Outward: **LiteLLM v1.109.0
  stable** (982 PRs, disk-cache backend removed, 5 action-required) +
  **1.108.5 LTS**; 1.110.0-rc.1 and Ollama 0.40.17-rc0 → watch; MCP
  file-uploads draft extension → watch. Converted inward: honest
  `stop_reason` incl. `pause_turn`/`max_tokens`/`refusal` (row 365 —
  facade always answers `end_turn` today), guardrail scan of assistant
  `tool_calls` arguments + opt-in system scan (366), streamed L0
  tool_calls fidelity (367), compare 1.109.0 floor + disk-cache
  positioning (368), overnight fence (369). Verified parity: mid-stream
  fallback continuation, session repin after failover,
  `prompt_cache_retention`, `redacted_thinking`, stream resume.
  Coding-router recipe trigger fired — file next run.

- **2026-11-09 → 11-10 pm** — Condensed: Kong 2.3.0 deep cut (rows
  345–349: drop_block binding, tool billing, pre-charge, per-key Prom
  label); Fable/Mythos 5.2 cliff (350–354: catalog + fast mode, thinking
  strip, toolset gate, baggage PATCH); reasoning fidelity + tenant BYOK
  + truncation (355–359, on LiteLLM 1.108.4 LTS + Ollama 0.40.16);
  residency/auto_caching/5xx/advisor converts (360–364). Verified then:
  5xx hard-fails the breaker; no `background` billing leak; facade list
  shapes fine.

- **2026-11-08 → 11-08 pm** — Condensed: MCP egress fidelity + Kong
  2.3.0 parity (rows 335–339, filed off the 1.108.3 LTS MCP >1 MiB SSE
  fix); 1.110-dev credential patterns + Claude `effort=none` converts
  (340, 342) + forensics ownership (341) + cost Prom/stats (343) +
  fence (344).

- **2026-11-07 → 11-07 pm** — Condensed: Auto-Router converts + PG-blip
  grace (rows 326–329; adopted dead Actions PR rows 321–325); observe +
  compare tail (330–334: SLO demotion Grafana, compare floors, OTel tags
  ownership). Issue #2141 still needs human close.

- **2026-11-06 → 10-28** — Condensed: leaked-key blast radius + Ollama
  0.40.15 GA (rows 316–325; dead Actions PR #2127 drained, stall issue
  #2141 needs human close); TTFT/SLO observe tail (311–315); governance
  console / Codex PAT / admission Prom; Ollama 0.40.14 parity;
  message-threads / TPD / selection Grafana; trace cost / latency SLO /
  vLLM / MCP cc; LTS / air-gap / batch default / request tags; through
  Apache 2.0 and this PRD's creation.
