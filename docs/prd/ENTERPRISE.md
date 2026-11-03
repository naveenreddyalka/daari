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

## Where daari stands (verified in-tree, 2026-11-03 pm)

**Loop velocity.** Afternoon: service-tier allowlist + `lfm3-audio` recipe
Shipped (#2108–#2109). Morning filed Ollama 0.40.14 parity rows 296–300
(#2102–#2106) still open. Overnight TPD / priority / batch webhooks remain
Shipped (#2091–#2092, #2099–#2101).

**Outward.** Landscape flat since morning: **Ollama 0.40.14** still top;
**LiteLLM first Tuesday cut still not landed** as of 11-03 20:22 UTC (top
tag 1.109.0-dev.2, GA floor **1.106.6**, LTS pilot 1.108 rc.1 only). Portkey
Enterprise floor **v2.32.0** (Codex PAT `at-` routing, Complete Logs
cost+metadata — cost attrs already filed as row 286). vLLM tag still
`v0.33.0rc3`. Anthropic message-threads public beta unchanged. OpenAI /
Kong / MCP spec unchanged this afternoon.

**Inward theme: finish the governance console after the dials ship.**
Allowlist enforcement is live but invisible in stats/Prom and admin/web-ui;
admission priority logs events with no scrape series; Portkey's Codex PAT
host switch is still a watch-turned-gap for L6; afternoon ships need a
hermetic fence beside the overnight priority/webhook fence.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 301 | Stats/Prom counters for `service_tier_not_allowed` deny + degrade | 3 | 1 | OpenAI Platform tier restriction analytics / LiteLLM spend | Governance cliffs on the same-box scrape | Filed [#2110](https://github.com/naveenreddyalka/daari/issues/2110) |
| 302 | Admin + web-ui surface for `allowed_service_tiers` | 3 | 1 | OpenAI Platform project tier UI / LiteLLM Admin | Same-box console for the dial CLI already mints | Filed [#2111](https://github.com/naveenreddyalka/daari/issues/2111) |
| 303 | Route Codex PATs (`at-`) to the Codex backend on L6 | 3 | 2 | Portkey v2.32.0 OpenAI integration | Local tiers still win before Codex egress | Filed [#2112](https://github.com/naveenreddyalka/daari/issues/2112) |
| 304 | Prometheus counter for `X-Daari-Priority` admission overrides | 2 | 1 | LiteLLM / Portkey priority dashboards | Queue-steer pressure without a SaaS log plane | Filed [#2113](https://github.com/naveenreddyalka/daari/issues/2113) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio recipe | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 296 | Omitted `temperature` must inherit backend sampler defaults | 4 | 2 | Ollama 0.40.14 OpenAI-compat fix | Keep daari-in-front-of-Ollama byte-equivalent to Ollama direct | Filed [#2102](https://github.com/naveenreddyalka/daari/issues/2102) |
| 297 | Batches webhook family in rotation CLI + doctor | 3 | 1 | — (finish #2101) | Every push channel signed and rotatable on-box | Filed [#2103](https://github.com/naveenreddyalka/daari/issues/2103) |
| 298 | Facade `/api/show` context + output-token limits | 3 | 2 | Ollama 0.40.14 `launch claude` | Report the routed tier's real limits, per virtual model | Filed [#2104](https://github.com/naveenreddyalka/daari/issues/2104) |
| 299 | Preserve assistant refusal parts in Responses input | 2 | 1 | Ollama 0.40.14 `/v1/responses` fix | Refusals survive tier hops; shape fidelity is daari's job | Filed [#2105](https://github.com/naveenreddyalka/daari/issues/2105) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 291 | Anthropic message-threads create/continue passthrough | 4 | 3 | Anthropic Claude Platform / Claude Code default | L6 keeps Anthropic TTFT win; L0/L1 still beat threads on repeats | Filed [#2093](https://github.com/naveenreddyalka/daari/issues/2093) |
| 292 | Web-ui TPD / user_tpd on admin keys/teams + copy | 3 | 1 | LiteLLM Admin key/team caps UI | Same-box console for the dial CLI/Prom already expose | Filed [#2094](https://github.com/naveenreddyalka/daari/issues/2094) |
| 293 | Grafana panel for `daari_virtual_model_selection_total{mode}` | 2 | 1 | OpenRouter performance analytics | Chart on-box TTFT EWMA mode next to failover | Filed [#2095](https://github.com/naveenreddyalka/daari/issues/2095) |
| 294 | Split rate_limit soft_warnings/rejects by rpm/tpm/rpd/tpd | 3 | 2 | LiteLLM spend / rate dashboards | Name the dial that cliffed without a log pipeline | Filed [#2096](https://github.com/naveenreddyalka/daari/issues/2096) |
| 295 | Integration fence for the 11-02 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: TPD admission + OpenRouter compare pin | Filed [#2097](https://github.com/naveenreddyalka/daari/issues/2097) |
| 286 | Cost + key/team attributes on OTel GenAI spans | 3 | 2 | Portkey v2.32.0 Complete Logs export | Per-tenant cost traces in operator-owned OTel backend | Filed [#2085](https://github.com/naveenreddyalka/daari/issues/2085) |
| 287 | Latency SLO bucketing for performance virtual-model selection | 3 | 2 | OpenRouter rebuilt provider routing | SLO sees local-tier latencies no cloud router can | Filed [#2086](https://github.com/naveenreddyalka/daari/issues/2086) |
| 288 | vLLM 0.33 upgrade notes (CUDA 13-only, image alias) | 2 | 1 | vLLM release notes | Honest local-tier upgrade before operators hit it | Filed [#2087](https://github.com/naveenreddyalka/daari/issues/2087) |
| 289 | Document MCP client-credentials upstream via `secret://oauth` | 2 | 1 | Portkey v2.32.0 MCP OAuth config | Capability exists on-box; the recipe is the gap | Filed [#2088](https://github.com/naveenreddyalka/daari/issues/2088) |
| 290 | Integration fence for the 11-01/11-02 overnight wave | 2 | 2 | — (testability) | Hermetic proof: signals binding, PATCH, perf mode, fast shield | Filed [#2089](https://github.com/naveenreddyalka/daari/issues/2089) |
| 281 | compare-litellm: LTS 1.108 pilot + Tuesday cadence honesty | 2 | 1 | LiteLLM LTS / release-cycle docs | Name the support window; keep GA floor 1.106.6 | Filed [#2075](https://github.com/naveenreddyalka/daari/issues/2075) |
| 282 | Config ownership + PATCH for `security.offline_mode` | 3 | 1 | LiteLLM / Portkey control planes | Flip the air gap live, no restart, no cloud plane | Filed [#2076](https://github.com/naveenreddyalka/daari/issues/2076) |
| 283 | Org-default completion webhook for `/v1/batches` | 3 | 2 | OpenRouter Default batch webhook URL | Mirror Responses org default on-box | Filed [#2077](https://github.com/naveenreddyalka/daari/issues/2077) |
| 284 | Request tags matchable by `signal_overrides` | 3 | 2 | LiteLLM tag routing / Portkey Signals | Workload tags steer local levers without new keys | Filed [#2078](https://github.com/naveenreddyalka/daari/issues/2078) |
| 285 | Doctor tip: offline_mode on + live frontier L6 creds | 2 | 1 | — (ops honesty) | Same-box warning before the 403 storm | Filed [#2079](https://github.com/naveenreddyalka/daari/issues/2079) |
| 277–278 | Service-tier allowlist; `lfm3-audio` speech-only recipe | 2–3 | 1–2 | OpenAI / Ollama | Deny 6× tiers; speech without omni weights | Shipped (#2108–#2109) |
| 279 | Prometheus counter for offline-mode refused egress | 2 | 1 | — (ops honesty) | Prove the air gap held from the same box's scrape | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072) |
| 280 | Integration fence for the 10-31/11-01 overnight wave | 2 | 2 | — (testability) | Hermetic proof: reconcile, offline, audio, safeguard | Filed [#2073](https://github.com/naveenreddyalka/daari/issues/2073) |
| 271–273, 275–276 | TPD quotas; OpenRouter + LiteLLM compare honesty; priority header; signed batch webhooks | 2–3 | 1–2 | LiteLLM / OpenRouter | Day-grain dial, honest copy, queue steer, signed push on-box | Shipped (#2091–#2092, #2099–#2101) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 266–269 | Tenant signal binding; virtual_models PATCH; performance selection; Opus 4.8 fast shield | 3–4 | 1–3 | Portkey / LiteLLM / OpenRouter / Anthropic | Tenant levers + realized perf + deprecation shield | Shipped (#2081–#2084) |
| 270 | Integration fence for the 10-30/31 overnight wave | 2 | 2 | — (testability) | Hermetic proof: virtual models, hour bucket, PATCHes | Filed [#2054](https://github.com/naveenreddyalka/daari/issues/2054) |
| 258–264 | safeguard; Analytics reconcile; offline_mode; OpenRouter CSAM/Private; MCP SEP-3392; LFM3-VL; lfm3-omni | 2–4 | 1–3 | OpenRouter / Anthropic / LiteLLM / MCP / Ollama | Guardrails, FinOps, air-gap, honesty, omni local | Shipped (#2062–#2068) |
| 251–257 | LiteLLM GA / team_metrics / virtual models / hour buckets / body-cap | 2–4 | 1–3 | LiteLLM / Portkey / ngrok | Honest floor + FinOps + failover | Mixed (most Shipped; 252/254 Filed) |
| 242–250 | LiteLLM-1.109 ride-along; LFM3 Linux; signal_overrides validate/PATCH/Grafana | 2–4 | 1–3 | LiteLLM / Ollama / Portkey | Mid-stream, agent deny, local tier, live Signals | Mixed (many Shipped; 250 Filed) |
| 225–241 | Prom/Grafana/doctor honesty + Portkey/llama.cpp/LFM3 | 2–4 | 1–3 | Portkey / llama.cpp / Ollama | Operator-owned on-box | Mixed (many Shipped; 225–226, 236, 1987 Filed) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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

Watch rows (do not file yet): minute-grain spend buckets (**deliberately
scoped out in hour-bucket work**); fleet-shared Redis EWMA for performance
selection (per-pod in-process by #2083 design); **LiteLLM first Tuesday cut**
(still not landed by 11-03 20:22 UTC — refresh compare when 1.108 stable /
next RC lands); MCP SEP-3398 (next spec ~March 2027); OpenAI org external
key management; Anthropic Compliance API user-preferences export; Models API
`between_tools` still Sonnet-5.5-only; `gpt-6-rosalind` catalog
(trusted-access only); Claude Code gateway-upstream `groups` /
`guardrail_trace` passthrough; MCP SEP-3392 docs-link refresh; OpenRouter
private-provider CRUD + S3/IAM destinations; LiteLLM Admin Chat UI / Lens
(non-goal); llama.cpp `/v1/realtime` + `POST /tts`; llama.cpp deferred tools
+ `tool_reference`; Portkey claim-based JWT; OpenAI `/agents/automations`
passthrough; Prisma AIRS Agent Identity; Claude-on-GCP IAM egress (new dep —
human sign-off); Anthropic hosted `/v1/skills` proxy; Claude Tag beta
(non-goal); Open Responses WS; Anthropic OTel export beta; Prometheus
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate; Portkey WIF;
SCIM + multi-issuer SSO; Kong Skills/A2A; OpenRouter Private Endpoints L6
recipe; certifi emSign drop; Ollama d1 Linux/Windows GA; local
message-thread analogue (prefix store for continue on L3–L5 — file only on
explicit agent-loop ask after row 291 ships).

Verified fine this run — don't re-audit: admin inventory already exposes
`tpd`/`user_tpd`/`priority`/`signal_overrides` (gap = service-tier dial only,
row 302); `service_tier_not_allowed` events log but do not bump
rejects/soft_warnings (row 301); `admission_priority` events log without a
Prom series (row 304); frontier always uses configured `base_url` for every
Bearer key (row 303); **all executors already guard `temperature is not
None`** (row 296 ingress-only); batches dual-secret verify present (row
297); facade thinking + ≥0.40.7 show fields current; Ollama `launch codex` /
ChatGPT retry not daari surface; guardrail soft-deny-200 default; MCP
`secret://oauth` capability live (docs = row 289); TPD Prom `kind="tpd"`
gauges live; `AnthropicRequest` still has **no `thread` field** (row 291);
LiteLLM GA floor 1.106.6.

---

## Path to enterprise-grade — next 5 milestones

1. **Governance console after the dials** — service-tier Prom (301) +
   admin/web-ui (302); TPD web-ui (292); rate-limit kind split (294); then
   rows 62–67.
2. **Byte-equivalence with the local runtime (Ollama 0.40.14 bar)** —
   sampler-default honesty (296); facade limits (298); Responses refusal
   fidelity (299); fences (300, 305).
3. **Claude Code TTFT parity on-box** — message-threads passthrough (291);
   keep L0/L1 as the local answer when history repeats.
4. **Answer OpenRouter's performance router** — selection shipped (268);
   latency SLO (287); selection Grafana (293); failover Grafana (274);
   admission Prom (304).
5. **Air-gap + jobs + honesty tail** — Codex PAT L6 host (303); offline
   ownership (282); doctor tip (285); Prom counter (279); batch org-default
   webhook (283) + rotation family (297); vLLM 0.33 notes (288); LiteLLM
   LTS (281) + Tuesday watch; hot-reload (6).

---

## Changelog

- **2026-11-03 pm (governance console; Codex PAT; admission Prom; afternoon fence)** —
  Marked rows 277–278 Shipped (#2108–#2109). Outward flat: LiteLLM Tuesday
  cut still absent at 20:22 UTC; Portkey v2.32.0 Codex PAT routing pulled
  off the watch list into a filed gap. Filed rows 301–305: service-tier
  stats/Prom, admin/web-ui allowlist columns, Codex `at-` L6 host switch,
  admission-priority Prom counter, 11-03 afternoon fence. Verified: admin
  inventory omits allowlist; deny/degrade log without stats kinds;
  frontier base_url is key-prefix-blind.

- **2026-11-03 (Ollama 0.40.14 parity: sampler defaults, facade limits, refusals; batches rotation)** —
  Marked rows 271–273, 275–276 Shipped (#2091–#2092, #2099–#2101). Adopted
  rows 291–295 from the unmerged 11-02 pm sibling PR. Filed rows 296–300.

- **2026-11-02 pm → 10-28** — Condensed: message-threads / TPD console /
  selection Grafana / rate-limit scope; trace cost / latency SLO / vLLM
  0.33 / MCP cc; LTS honesty / air-gap ops / batch default / request tags;
  governance dials / batch webhooks; TPD / OpenRouter router / admission
  priority; performance routing / tenant signals; FinOps / air-gap /
  virtual models / Portkey / llama.cpp through Apache 2.0 and this PRD's
  creation.
