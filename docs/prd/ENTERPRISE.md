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

## Where daari stands (verified in-tree, 2026-11-05)

**Loop velocity.** Since the 11-03 pm PRD: TTFT / console dials landed —
message-threads (#2130), TPD web-ui (#2131), selection Grafana (#2132),
latency SLO (#2121), OTel cost/tenant (#2120), request tags (#2119), batches
org webhook (#2118), offline_mode PATCH (#2117), LiteLLM LTS compare
(#2116), vLLM 0.33 notes (#2128), MCP `secret://oauth` recipe (#2129).
Nov-4 refill (#2122–#2126) was filed without an ENTERPRISE merge — adopted
below as rows 306–310. Governance Prom / allowlist console / Codex PAT /
Ollama 0.40.14 parity rows 296–305 remain open.

**Outward.** **LiteLLM v1.108.0** LTS GA (2026-11-04) + **1.106.7** patch +
**1.109.0-rc.1** watch (floor promote already filed row 306). **Portkey
Enterprise v2.33.0** (2026-11-04): Anthropic `auto_caching`, OTel
`user_agent.original` + workspace name, MCP access policies GA (Prisma AIRS),
Bedrock metadata map — UA export pulled into a filed gap; auto_caching /
MCP policies stay Watch (daari already has `frontier.prompt_cache`).
**Ollama 0.40.15-rc1** only (MiMo V2.6 + mlx Linux CUDA libs) — not GA.
**vLLM** still `v0.33.0rc3` on GitHub tags (docs already cover 0.33 GA notes).
OpenRouter / Kong / MCP spec unchanged this run.

**Inward theme: observe and console what just shipped.** Threads, SLO ms, and
Portkey's new OTel UA attribute are live dials with no scrape/console/privacy
tail; LiteLLM's requester-IP omit dial has no daari twin on enterprise audit.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 311 | Stats/Prom for Anthropic message-threads create/continue/soft-ignore | 3 | 1 | Anthropic Claude Platform / Claude Code | Chart L6 thread pressure vs local fail-closed on-box | Filed [#2133](https://github.com/naveenreddyalka/daari/issues/2133) |
| 312 | Opt-in `user_agent` on OTel GenAI spans | 3 | 1 | Portkey v2.33.0 Complete Logs | IDE/agent attribution in operator-owned OTel | Filed [#2134](https://github.com/naveenreddyalka/daari/issues/2134) |
| 313 | Admin + web-ui surface for `virtual_model_latency_slo_ms` | 3 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box console for the SLO dial selection already uses | Filed [#2135](https://github.com/naveenreddyalka/daari/issues/2135) |
| 314 | Opt-in omit requester `client_ip` from enterprise audit | 3 | 2 | LiteLLM 1.108.0 `disable_requester_ip_address_logging` | Privacy dial on operator-owned audit disk | Filed [#2136](https://github.com/naveenreddyalka/daari/issues/2136) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 306 | compare-litellm: promote GA floor to 1.108.0 LTS; note 1.109.0-rc.1 | 2 | 1 | LiteLLM LTS / release notes | Honest support window; no proxy pin | Filed [#2122](https://github.com/naveenreddyalka/daari/issues/2122) |
| 307 | Prom/stats counters for virtual-model latency SLO demotions | 3 | 1 | OpenRouter performance router analytics | SLO pressure from on-box EWMA | Filed [#2123](https://github.com/naveenreddyalka/daari/issues/2123) |
| 308 | Opt-in request tags on OTel GenAI spans | 3 | 1 | Portkey Complete Logs / LiteLLM tag dashboards | Workload tags next to local-tier cost attrs | Filed [#2124](https://github.com/naveenreddyalka/daari/issues/2124) |
| 309 | Config ownership + PATCH for `routing.virtual_model_latency_slo_ms` | 3 | 1 | LiteLLM / OpenRouter control planes | Hot-edit SLO ms without restart | Filed [#2125](https://github.com/naveenreddyalka/daari/issues/2125) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: prior overnight dials | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 301 | Stats/Prom counters for `service_tier_not_allowed` deny + degrade | 3 | 1 | OpenAI Platform / LiteLLM spend | Governance cliffs on the same-box scrape | Filed [#2110](https://github.com/naveenreddyalka/daari/issues/2110) |
| 302 | Admin + web-ui surface for `allowed_service_tiers` | 3 | 1 | OpenAI Platform / LiteLLM Admin | Same-box console for the dial CLI already mints | Filed [#2111](https://github.com/naveenreddyalka/daari/issues/2111) |
| 303 | Route Codex PATs (`at-`) to the Codex backend on L6 | 3 | 2 | Portkey v2.32.0 OpenAI integration | Local tiers still win before Codex egress | Filed [#2112](https://github.com/naveenreddyalka/daari/issues/2112) |
| 304 | Prometheus counter for `X-Daari-Priority` admission overrides | 2 | 1 | LiteLLM / Portkey priority dashboards | Queue-steer pressure without a SaaS log plane | Filed [#2113](https://github.com/naveenreddyalka/daari/issues/2113) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 296 | Omitted `temperature` must inherit backend sampler defaults | 4 | 2 | Ollama 0.40.14 OpenAI-compat fix | Keep daari-in-front-of-Ollama byte-equivalent | Filed [#2102](https://github.com/naveenreddyalka/daari/issues/2102) |
| 297 | Batches webhook family in rotation CLI + doctor | 3 | 1 | — (finish batch webhooks) | Every push channel signed and rotatable on-box | Filed [#2103](https://github.com/naveenreddyalka/daari/issues/2103) |
| 298 | Facade `/api/show` context + output-token limits | 3 | 2 | Ollama 0.40.14 `launch claude` | Report the routed tier's real limits | Filed [#2104](https://github.com/naveenreddyalka/daari/issues/2104) |
| 299 | Preserve assistant refusal parts in Responses input | 2 | 1 | Ollama 0.40.14 `/v1/responses` fix | Refusals survive tier hops | Filed [#2105](https://github.com/naveenreddyalka/daari/issues/2105) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 291–293 | Message-threads; TPD web-ui; selection Grafana | 2–4 | 1–3 | Anthropic / LiteLLM / OpenRouter | TTFT parity + same-box console | Shipped (#2130–#2132) |
| 286–289 | OTel cost attrs; latency SLO; vLLM 0.33 notes; MCP oauth recipe | 2–3 | 1–2 | Portkey / OpenRouter / vLLM | Operator-owned traces + honest local tiers | Shipped (#2120–#2121, #2128–#2129) |
| 281–284 | LiteLLM LTS compare; offline PATCH; batch org webhook; request tags | 2–3 | 1–2 | LiteLLM / OpenRouter / Portkey | Honesty + air-gap + jobs + Signals on-box | Shipped (#2116–#2119) |
| 294 | Split rate_limit soft_warnings/rejects by rpm/tpm/rpd/tpd | 3 | 2 | LiteLLM spend / rate dashboards | Name the dial that cliffed | Filed [#2096](https://github.com/naveenreddyalka/daari/issues/2096) |
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
| 277–278 | Service-tier allowlist; `lfm3-audio` speech-only recipe | 2–3 | 1–2 | OpenAI / Ollama | Deny 6× tiers; speech without omni weights | Shipped (#2108–#2109) |
| 271–273, 275–276 | TPD quotas; OpenRouter + LiteLLM compare; priority; signed batch webhooks | 2–3 | 1–2 | LiteLLM / OpenRouter | Day-grain dial, honest copy, queue steer | Shipped (#2091–#2092, #2099–#2101) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): Portkey v2.33 Anthropic `auto_caching` (daari
`frontier.prompt_cache` already marks system blocks — revisit only if
top-level `cache_control` shape diverges in client traffic); Portkey MCP
access policies (Prisma AIRS-only); Portkey OTel workspace name; Bedrock
metadata map; LiteLLM OpenAI Live `/v1/live/sessions` + Azure PTU split +
M365 Copilot provider (Realtime/WS family); LiteLLM 1.109.0 stable cut;
Ollama 0.40.15 GA / MiMo V2.6 recipe; minute-grain spend buckets; fleet
Redis EWMA; MCP SEP-3398 (~March 2027); OpenAI org external key management;
Anthropic Compliance API; Models API `between_tools` Sonnet-5.5-only;
`gpt-6-rosalind` catalog; Claude Code `groups` / `guardrail_trace`;
OpenRouter private-provider CRUD + S3/IAM; LiteLLM Admin Chat UI / Lens;
llama.cpp `/v1/realtime` + `POST /tts` + deferred tools; Portkey
claim-based JWT / WIF; OpenAI `/agents/automations`; Prisma AIRS Agent
Identity; Claude-on-GCP IAM (new dep — human); Anthropic hosted skills;
Claude Tag beta; Open Responses WS; Anthropic OTel export beta; Prom
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer SSO;
Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign;
Ollama d1 Linux/Windows GA; local message-thread analogue (prefix store on
L3–L5 — only after explicit agent-loop ask).

Verified fine this run — don't re-audit: message-threads create/continue +
soft-ignore + beta header live (gap = counters, row 311); TPD/user_tpd on
admin inventory + web-ui; selection Grafana `mode` panel live; latency SLO
map ranks EWMA (gaps = demotion Prom 307, PATCH 309, console 313); OTel
exports cost + key/team (gaps = tags 308, UA 312); `frontier.prompt_cache`
marks Anthropic system `cache_control`; audit persists `client_ip` with no
omit dial (row 314); LiteLLM floor still 1.106.6 in compare until row 306
lands; Ollama top stable **0.40.14** (0.40.15 still rc1); Portkey floor
**v2.33.0**.

---

## Path to enterprise-grade — next 5 milestones

1. **Observe the TTFT / SLO dials** — thread counters (311); SLO demotion
   Prom (307) + PATCH (309) + console (313); selection Grafana shipped.
2. **Governance console tail** — service-tier Prom (301) + admin/web-ui
   (302); rate-limit kind split (294); then rows 62–67.
3. **OTel / privacy parity with Portkey 2.33 + LiteLLM 1.108** — UA spans
   (312); request-tag spans (308); audit IP omit (314).
4. **Byte-equivalence with Ollama 0.40.14** — sampler defaults (296);
   facade limits (298); Responses refusals (299); fences (300, 305, 310,
   315); watch 0.40.15 GA.
5. **Air-gap + jobs + honesty** — Codex PAT L6 host (303); offline Prom
   (279) + doctor (285); batches rotation (297); admission Prom (304);
   LiteLLM 1.108 floor (306) + 1.109 watch; hot-reload (6).

---

## Changelog

- **2026-11-05 (TTFT/SLO observe tail; Portkey 2.33 UA; LiteLLM IP omit; catch-up)** —
  Marked rows 281–284, 286–289, 291–293 Shipped. Adopted Nov-4 filings as
  rows 306–310 (LiteLLM 1.108 floor, SLO demotion Prom, OTel tags, SLO
  PATCH, fence). Outward: LiteLLM 1.108.0 LTS GA + 1.109.0-rc.1; Portkey
  v2.33.0; Ollama 0.40.15-rc1 only. Filed rows 311–315: thread stats/Prom,
  OTel user_agent, latency_slo console, audit client_ip omit, 11-04/11-05
  fence. Verified: threads/SLO/TPD/selection live without scrape/console
  tails; audit always stores client_ip; prompt_cache covers auto_caching
  watch.

- **2026-11-03 pm → 10-28** — Condensed: governance console / Codex PAT /
  admission Prom; Ollama 0.40.14 parity; message-threads / TPD / selection
  Grafana; trace cost / latency SLO / vLLM / MCP cc; LTS / air-gap / batch
  default / request tags; through Apache 2.0 and this PRD's creation.
