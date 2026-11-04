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

## Where daari stands (verified in-tree, 2026-11-04)

**Loop velocity.** Overnight/morning: LTS compare honesty, offline_mode PATCH,
batches org-default webhook, request-tag signal_overrides, OTel cost+tenant
attrs, latency SLO bucketing — Shipped (#2116–#2121 / #2075–#2078,
#2085–#2086). Afternoon 11-03 governance dials + speech recipe remain
Shipped (#2108–#2109). Ollama 0.40.14 parity + batches rotation rows
296–300 and governance console rows 301–305 still open.

**Outward.** **LiteLLM Tuesday cut landed:** stable **[v1.108.0](https://github.com/BerriAI/litellm/releases/tag/v1.108.0)**
(2026-11-04 03:35 UTC) is the LTS pilot GA line; patch **1.106.7** and
prerelease **1.109.0-rc.1** also cut the same morning. compare-litellm still
pins floor **1.106.6** / frames 1.108 as RC-only (gap → row 306). Portkey
Enterprise floor still **v2.32.0**. Ollama stable still **0.40.14**;
**0.40.15-rc0** adds MiMo V2.6 + Linux MLX CUDA in-process (watch until GA).
vLLM top tag still `v0.33.0rc3`. Anthropic message-threads public beta
unchanged. OpenRouter performance-router rebuild already reflected (row 287
shipped). Kong / MCP spec unchanged this run.

**Inward theme: instrument and own the performance + tag dials after they
ship; refresh compare for LiteLLM LTS GA.** Latency SLO demotes without a
Prom series; OTel still omits request tags by design comment; SLO map is
YAML-restart-only beside live `virtual_models` ownership; morning wave needs
a hermetic fence.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 306 | compare-litellm: promote GA floor to 1.108.0 LTS; note 1.109.0-rc.1 + 1.106.7 | 3 | 1 | LiteLLM LTS / release-cycle docs | Honest support window; no weekly proxy train on-box | Filed [#2122](https://github.com/naveenreddyalka/daari/issues/2122) |
| 307 | Stats/Prom counters for virtual-model latency SLO demotions | 3 | 1 | OpenRouter performance router analytics | Chart on-box SLO pressure next to selection mode | Filed [#2123](https://github.com/naveenreddyalka/daari/issues/2123) |
| 308 | Opt-in request tags on OTel GenAI spans | 3 | 1 | Portkey Complete Logs / LiteLLM tag routing | Workload tags beside local cost attrs in operator OTel | Filed [#2124](https://github.com/naveenreddyalka/daari/issues/2124) |
| 309 | Config ownership + PATCH for `virtual_model_latency_slo_ms` | 3 | 1 | LiteLLM / OpenRouter control planes | Hot-edit the ms dial next to live `virtual_models` | Filed [#2125](https://github.com/naveenreddyalka/daari/issues/2125) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: offline PATCH, batch default, tags, OTel, SLO | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 301 | Stats/Prom counters for `service_tier_not_allowed` deny + degrade | 3 | 1 | OpenAI Platform / LiteLLM spend | Governance cliffs on the same-box scrape | Filed [#2110](https://github.com/naveenreddyalka/daari/issues/2110) |
| 302 | Admin + web-ui surface for `allowed_service_tiers` | 3 | 1 | OpenAI Platform / LiteLLM Admin | Same-box console for the dial CLI already mints | Filed [#2111](https://github.com/naveenreddyalka/daari/issues/2111) |
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
| 281–287 | LiteLLM LTS honesty; offline PATCH; batch default webhook; request tags; OTel cost attrs; latency SLO | 2–3 | 1–2 | LiteLLM / Portkey / OpenRouter | Air-gap ops, jobs, tags, chargeback, SLO on-box | Shipped (#2116–#2121) |
| 288 | vLLM 0.33 upgrade notes (CUDA 13-only, image alias) | 2 | 1 | vLLM release notes | Honest local-tier upgrade before operators hit it | Filed [#2087](https://github.com/naveenreddyalka/daari/issues/2087) |
| 289 | Document MCP client-credentials upstream via `secret://oauth` | 2 | 1 | Portkey v2.32.0 MCP OAuth config | Capability exists on-box; the recipe is the gap | Filed [#2088](https://github.com/naveenreddyalka/daari/issues/2088) |
| 290 | Integration fence for the 11-01/11-02 overnight wave | 2 | 2 | — (testability) | Hermetic proof: signals binding, PATCH, perf mode, fast shield | Filed [#2089](https://github.com/naveenreddyalka/daari/issues/2089) |
| 277–280 | Service-tier allowlist; lfm3-audio; offline Prom; overnight fence | 2–3 | 1–2 | OpenAI / Ollama | Deny dials + speech + air-gap scrape | Mixed (277–278 Shipped; 279–280 Filed) |
| 271–276 | TPD quotas; OpenRouter + LiteLLM compare; priority; signed batch webhooks | 2–3 | 1–2 | LiteLLM / OpenRouter | Day-grain dial, honest copy, queue steer, signed push | Shipped (#2091–#2092, #2099–#2101) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 266–270 | Tenant signals; virtual_models PATCH; performance selection; Opus shield; fence | 2–4 | 1–3 | Portkey / LiteLLM / OpenRouter / Anthropic | Tenant levers + realized perf | Mixed (266–269 Shipped; 270 Filed) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): minute-grain spend buckets (**deliberately
scoped out in hour-bucket work**); fleet-shared Redis EWMA for performance
selection (per-pod in-process by #2083 design); **Ollama 0.40.15 / MiMo V2.6**
(file setup recipe only after stable, not rc0); **LiteLLM 1.109.0-rc.1 →
stable** (ride-along after floor moves to 1.108.0); Grafana panel for SLO
demotion series (file after row 307 ships); ownership for
`virtual_model_selection` enum (sibling to 309); MCP SEP-3398 (~March 2027);
OpenAI org external key management; Anthropic Compliance API
user-preferences export; Models API `between_tools` still Sonnet-5.5-only;
`gpt-6-rosalind` catalog (trusted-access only); Claude Code gateway-upstream
`groups` / `guardrail_trace` passthrough; MCP SEP-3392 docs-link refresh;
OpenRouter private-provider CRUD + S3/IAM destinations; LiteLLM Admin Chat
UI / Lens (non-goal); llama.cpp `/v1/realtime` + `POST /tts`; llama.cpp
deferred tools + `tool_reference`; Portkey claim-based JWT; OpenAI
`/agents/automations` passthrough; Prisma AIRS Agent Identity; Claude-on-GCP
IAM egress (new dep — human sign-off); Anthropic hosted `/v1/skills` proxy;
Claude Tag beta (non-goal); Open Responses WS; Anthropic OTel export beta;
Prometheus exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate;
Portkey WIF; SCIM + multi-issuer SSO; Kong Skills/A2A; OpenRouter Private
Endpoints L6 recipe; certifi emSign drop; Ollama d1 Linux/Windows GA; local
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
`virtual_model_latency_slo_ms` ranks in `virtual_models.py` with
`slo_demoted` on snapshot but **no Prom counter** (row 307); OTel comment
defers `req_meta.tags` (row 308); ownership `_FIELD_PATHS` has
`virtual_models` + `offline_mode` but **not** `virtual_model_latency_slo_ms`
(row 309); compare-litellm floor still **1.106.6** despite 1.108.0 GA (row
306); vLLM still `v0.33.0rc3` (row 288 notes still valid).

---

## Path to enterprise-grade — next 5 milestones

1. **Governance console after the dials** — service-tier Prom (301) +
   admin/web-ui (302); TPD web-ui (292); rate-limit kind split (294); then
   rows 62–67.
2. **Byte-equivalence with the local runtime (Ollama 0.40.14 bar)** —
   sampler-default honesty (296); facade limits (298); Responses refusal
   fidelity (299); fences (300, 305, 310). Watch 0.40.15/MiMo until GA.
3. **Claude Code TTFT parity on-box** — message-threads passthrough (291);
   keep L0/L1 as the local answer when history repeats.
4. **Answer OpenRouter's performance router** — selection + SLO shipped
   (268, 287); SLO Prom (307) + ownership (309); selection Grafana (293);
   failover Grafana (274); admission Prom (304); OTel tags (308).
5. **Air-gap + jobs + honesty tail** — LiteLLM 1.108.0 LTS floor (306);
   Codex PAT L6 host (303); doctor tip (285); Prom counter (279); batch
   rotation family (297); vLLM 0.33 notes (288); hot-reload (6).

---

## Changelog

- **2026-11-04 (LiteLLM 1.108.0 LTS GA; instrument SLO + tags after morning ships)** —
  Marked rows 281–287 Shipped (#2116–#2121). Outward: LiteLLM **v1.108.0**
  stable LTS + 1.106.7 + 1.109.0-rc.1; Ollama 0.40.15-rc0 MiMo watch; Portkey
  / vLLM / Anthropic threads unchanged. Filed rows 306–310: compare floor
  promotion, SLO demotion Prom, opt-in OTel request tags, latency_slo
  ownership PATCH, 11-04 morning fence. Verified: ownership omits SLO map;
  OTel defers tags; demotions stamp snapshot only; compare still 1.106.6.

- **2026-11-03 pm (governance console; Codex PAT; admission Prom; afternoon fence)** —
  Marked rows 277–278 Shipped (#2108–#2109). Outward flat pre-Tuesday cut.
  Filed rows 301–305.

- **2026-11-03 → 10-28** — Condensed: Ollama 0.40.14 parity / batches
  rotation; message-threads / TPD console / selection Grafana / rate-limit
  scope; trace cost / latency SLO / vLLM 0.33 / MCP cc; LTS honesty /
  air-gap ops / batch default / request tags; governance dials / batch
  webhooks; TPD / OpenRouter router / admission priority; performance
  routing / tenant signals; FinOps / air-gap / virtual models / Portkey /
  llama.cpp through Apache 2.0 and this PRD's creation.
