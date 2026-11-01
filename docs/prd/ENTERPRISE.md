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

## Where daari stands (verified in-tree, 2026-11-01 pm)

**Loop velocity.** Morning board (276–280) still Filed and open; no new
feature merges since #2074. Overnight wave 258–264 remains Shipped.

**Outward.** LiteLLM GA floor still **1.106.6**; newest tags
1.109.0-dev.2 / 1.108.0-rc.1. Fresh delta: LiteLLM's
[LTS pilot on 1.108](https://docs.litellm.ai/docs/enterprise/lts_pilot) and
Tuesday RC/stable cadence (week of 2026-11-02) — compare-litellm does not
name it yet. OpenRouter Batch docs emphasize workspace **Default batch
webhook URL** beside per-batch `callback_url` (daari has Responses org
default; batches do not). LiteLLM 1.109 action notes still push **tag
routing**. Ollama 0.40.13, vLLM **0.32.0** (no GA 0.33 on releases), Kong
3.9.4, Portkey floor v2.31.0 (docs cache still flakes to v2.20.0). Anthropic
`between_tools` stays Sonnet-5.5-only — watch, do not file. Claude Fable
5.1 already priced/catalogued in-tree.

**Inward theme: air-gap operability + jobs that finish without repeating
URLs + tag levers + compare honesty.** Offline mode shipped but is not
live-editable and doctor does not warn when frontier creds stay hot;
batches lack the Responses-style org default webhook; signal_overrides
cannot match request tags; compare-litellm lags the LTS story.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 281 | compare-litellm: LTS 1.108 pilot + Tuesday cadence honesty | 2 | 1 | LiteLLM LTS / release-cycle docs | Name the support window; keep GA floor 1.106.6 | Filed [#2075](https://github.com/naveenreddyalka/daari/issues/2075) |
| 282 | Config ownership + PATCH for `security.offline_mode` | 3 | 1 | LiteLLM / Portkey control planes | Flip the air gap live, no restart, no cloud plane | Filed [#2076](https://github.com/naveenreddyalka/daari/issues/2076) |
| 283 | Org-default completion webhook for `/v1/batches` | 3 | 2 | OpenRouter Default batch webhook URL | Mirror Responses org default on-box | Filed [#2077](https://github.com/naveenreddyalka/daari/issues/2077) |
| 284 | Request tags matchable by `signal_overrides` | 3 | 2 | LiteLLM tag routing / Portkey Signals | Workload tags steer local levers without new keys | Filed [#2078](https://github.com/naveenreddyalka/daari/issues/2078) |
| 285 | Doctor tip: offline_mode on + live frontier L6 creds | 2 | 1 | — (ops honesty) | Same-box warning before the 403 storm | Filed [#2079](https://github.com/naveenreddyalka/daari/issues/2079) |
| 276 | Signed completion webhooks for `/v1/batches` jobs | 3 | 2 | OpenRouter batches `callback_url` | Signed, on-box, offline-mode aware; Responses jobs already have it | Filed [#2069](https://github.com/naveenreddyalka/daari/issues/2069) |
| 277 | Per-key/team service-tier allowlist | 3 | 2 | OpenAI project service-tier restriction (10-21) | Deny/degrade 6× ultrafast at the gateway before spend | Filed [#2070](https://github.com/naveenreddyalka/daari/issues/2070) |
| 278 | `lfm3-audio` speech-only recipe | 2 | 1 | Ollama ≥0.40.12 lfm3-audio | On-box TTS/ASR without omni's vision+chat weights | Filed [#2071](https://github.com/naveenreddyalka/daari/issues/2071) |
| 279 | Prometheus counter for offline-mode refused egress | 2 | 1 | — (ops honesty) | Prove the air gap held from the same box's scrape | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072) |
| 280 | Integration fence for the 10-31/11-01 overnight wave | 2 | 2 | — (testability) | Hermetic proof: reconcile, offline, audio routing, safeguard | Filed [#2073](https://github.com/naveenreddyalka/daari/issues/2073) |
| 271 | Tokens-per-day (TPD) quota for keys/teams | 3 | 2 | LiteLLM 1.109.0-dev.2 daily token limits | Day-grain token dial next to RPD, on-box | Filed [#2056](https://github.com/naveenreddyalka/daari/issues/2056) |
| 272 | compare-openrouter: rebuilt performance-router honesty | 2 | 1 | OpenRouter 10-28 blog / provider-selection docs | Name the claim; point at on-box virtual models | Filed [#2057](https://github.com/naveenreddyalka/daari/issues/2057) |
| 273 | compare-litellm: 1.109.0-dev.2 watch + mid-stream honesty | 2 | 1 | LiteLLM release notes | Kill stale "next gap"; keep GA floor 1.106.6 | Filed [#2058](https://github.com/naveenreddyalka/daari/issues/2058) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 275 | Optional `X-Daari-Priority` request admission header | 3 | 2 | LiteLLM `x-litellm-priority` | Per-turn queue steer without minting keys | Filed [#2060](https://github.com/naveenreddyalka/daari/issues/2060) |
| 266 | Per-key/team binding for `signal_overrides` rules | 3 | 2 | Portkey workspace Signals / LiteLLM team settings | Tenant-scoped routing levers next to budgets, on-box | Filed [#2050](https://github.com/naveenreddyalka/daari/issues/2050) |
| 267 | Config ownership + PATCH for `routing.virtual_models` | 3 | 1 | LiteLLM / Portkey control planes | Edit failover lists live, no restart, no cloud plane | Filed [#2051](https://github.com/naveenreddyalka/daari/issues/2051) |
| 268 | Performance-aware virtual-model candidate selection | 4 | 3 | OpenRouter rebuilt provider routing (10-28) | Realized latency/error EWMA on-box, incl. local tiers | Filed [#2052](https://github.com/naveenreddyalka/daari/issues/2052) |
| 269 | Speed-scoped lifecycle: Opus 4.8 fast removal 11-30 shield | 3 | 2 | Anthropic release notes / client errors | Gateway warns then shields tenants before the hard 400 | Filed [#2053](https://github.com/naveenreddyalka/daari/issues/2053) |
| 270 | Integration fence for the 10-30/31 overnight wave | 2 | 2 | — (testability) | Hermetic proof: virtual models, hour bucket, PATCHes | Filed [#2054](https://github.com/naveenreddyalka/daari/issues/2054) |
| 261 | `lfm3-omni` recipe + audio capability routing matrix | 4 | 2 | Ollama lfm3-omni / cloud multimodal | One on-box model replaces ASR+VLM+LLM+TTS hops | Shipped (#2065) |
| 258–260 | safeguard recipe; Anthropic Analytics reconcile; offline_mode | 3–4 | 2–3 | OpenRouter / Anthropic / LiteLLM | On-box guardrails, FinOps proof, air-gap switch | Shipped (#2062–#2064) |
| 262–264 | compare-openrouter CSAM/Private; MCP SEP-3392 Beta; LFM3-VL notes | 2 | 1 | OpenRouter / MCP / Ollama | Honest copy at true maturity | Shipped (#2066–#2068) |
| 255–257 | Named virtual models; hour spend buckets; body-cap doctor | 2–4 | 1–3 | ngrok / Anthropic Analytics / — | Failover + FinOps honesty on-box | Shipped (#2047–#2049) |
| 251–254 | LiteLLM GA 1.106.6; team_metrics PATCH/Grafana/doctor | 2–3 | 1 | LiteLLM / Portkey | Honest floor + scrape cardinality | Mixed (251/253 Shipped; 252/254 Filed) |
| 247–250 | LFM3 Linux notes; signal_overrides validate/PATCH/Grafana | 2–3 | 1–2 | Ollama / Portkey | Local tier + live Signals | Mixed (247–249 Shipped; 250 Filed) |
| 242–246 | LiteLLM-1.109 ride-along (compare, mid-stream, agent deny, pricing, lfm3-vl) | 2–4 | 1–3 | LiteLLM / Ollama | Continue on next local hop; FinOps truth; vision local | Shipped (#2025–#2029) |
| 225–241 | Prom/Grafana/doctor honesty + Portkey/llama.cpp/LFM3 waves | 2–4 | 1–3 | Portkey / llama.cpp / Ollama | Operator-owned on-box | Mixed (many Shipped; 225–226, 236, 1987 Filed) |
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
scoped out in the hour-bucket work — row-blowup; only on an explicit FinOps
ask**); weighted/latency SLO knobs on virtual-model selection (after row
268); MCP SEP-3398 six-month release cycle (next spec late March 2027 —
docs date-pins only); OpenAI org
**external key management** (SDK 10-31 — pair with the at-rest EKM analog
when the Management API shape stabilizes beyond feature-flag); Anthropic
Compliance API user-preferences export (Enterprise Instructions/Cowork —
pair with erasure); Models API `between_tools` **still Sonnet-5.5-only**
(re-check if Anthropic widens); `gpt-6-rosalind` catalog entry
(trusted-access research only; price when GA); Claude Code
gateway-upstream `groups` / `guardrail_trace` passthrough (2.1.314 — IdP
claim→team mapping already in-tree); MCP SEP-3392 docs-link refresh when
extension repos rename; OpenRouter private-provider CRUD + S3/IAM
destinations; LiteLLM Admin Chat UI / Lens (non-goal); llama.cpp
`/v1/realtime` + `POST /tts` (pairs with row-8 Realtime/WS); llama.cpp
deferred tools + `tool_reference`; Portkey claim-based JWT; OpenAI
`/agents/automations` passthrough + Agents `compaction`/`experimental`/
session-review fields; Prisma AIRS Agent Identity; Claude-on-GCP IAM
egress (new dep — human sign-off); Anthropic hosted `/v1/skills` proxy;
Claude Tag beta (non-goal); Open Responses WS; Anthropic OTel export beta;
Prometheus exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate;
Portkey WIF; SCIM + multi-issuer SSO; Kong Skills/A2A; OpenRouter Private
Endpoints L6 recipe; certifi emSign drop (still ships 2026.10.23); Ollama
d1 Linux/Windows GA; rumored vLLM 0.33 tags without a releases GA note.

Verified fine this run — don't re-audit: **Claude Code pooled group
budgets (10-31) are parity** — key+team budget windows already merge
(`daari/auth/budgets.py` `effective_caps`); **Decisions facade already at
GA parity**; **ultrafast tier priced** at 6× (#1519);
**anthropic-version 2026-10-21 sampling/citations removal handled**;
`list_amount` vs discounted `amount` reconciled (#2063); Portkey changelog
cache flake — v2.31.0 stays the floor; LiteLLM GA floor 1.106.6; IdP
claim → team mapping exists; minute spend buckets stay scoped out;
**between_tools** not widened beyond Sonnet 5.5; Claude Fable 5.1 already
in pricing/catalog.

---

## Path to enterprise-grade — next 5 milestones

1. **Air-gap that operators can run** — offline switch (260 Shipped);
   live ownership (282); doctor foot-gun tip (285); Prom counter (279).
2. **Answer OpenRouter's performance router on-box** — virtual models
   (255 Shipped); performance-aware selection (268), live edit (267);
   performance-router compare copy (272).
3. **Tenant governance dials** — signals binding (266); request tags
   (284); service-tier allowlist (277); priority header (275); TPD
   (271); then rows 62–67.
4. **Jobs that finish loudly** — per-batch webhooks (276) + org default
   (283) beside Responses; fence the wave (280).
5. **Deprecation shield + honesty/ops tail** — Opus 4.8 fast removal
   shield (269); LiteLLM LTS/cadence honesty (281) + 1.109 refresh
   (273); virtual-model Grafana (274); hot-reload (6); P3 tail.

---

## Changelog

- **2026-11-01 pm (LTS honesty; air-gap ops; batch default; request tags)** —
  Outward: LiteLLM LTS 1.108 pilot + Tuesday cadence (week of 11-02);
  OpenRouter Default batch webhook URL; LiteLLM tag-routing action note;
  between_tools still Sonnet-5.5-only; vLLM GA floor stays 0.32.0.
  Filed rows 281–285: compare-litellm LTS honesty, offline_mode ownership,
  batches org-default webhook, request-tag signal_overrides, offline+L6
  doctor tip. Condensed shipped 247–264 blocks to reclaim line budget.
  Watch: keep between_tools; note unverified vLLM 0.33 tags.

- **2026-11-01 (governance dials; batch webhooks; air-gap telemetry)** —
  Marked rows 258–264 Shipped (#2062–#2068). Filed rows 276–280: batch
  completion webhooks, service-tier allowlist, `lfm3-audio`, offline-egress
  Prom counter, 10-31/11-01 wave fence. Watch pruned: `list_amount`,
  `lfm3-audio`; added MCP SEP-3398 March-2027 cycle.

- **2026-10-31 pm (1.109/OpenRouter honesty; TPD; request priority)** —
  Filed rows 271–275: TPD quotas, OpenRouter performance-router honesty,
  LiteLLM 1.109.0-dev.2 compare refresh, virtual-model failover Grafana,
  `X-Daari-Priority` admission header.

- **2026-10-31 → 10-28** — Condensed: performance-aware routing / tenant
  signals / deprecation shield; FinOps truth / air-gapped floor; team
  metrics / virtual models / Portkey v2.31.0 / llama.cpp v0.8.0 through
  Apache 2.0 and this PRD's creation.
