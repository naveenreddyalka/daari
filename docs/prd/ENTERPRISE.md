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

## Where daari stands (verified in-tree, 2026-11-02)

**Loop velocity.** Overnight wave 266–269 Shipped (#2081–#2084: tenant
signal binding, virtual_models PATCH, performance selection, Opus 4.8 fast
shield). Boards 270–285 stay Filed and open.

**Outward.** **vLLM 0.33.0 went GA 11-02** — CUDA 13.0-only artifacts
(cu129 images gone), PyTorch 2.14, new `vllm/vllm` image alias; daari's
vLLM guide stops at the 0.32 floor. **Portkey floor moves to v2.32.0**
(10-29): upstream-MCP OAuth client-credentials config, guardrail
`soft_deny_200`, OTel spans now carry `portkey.usage.cost` +
`portkey.metadata.*`, Codex PAT routing. LiteLLM GA floor still
**1.106.6** (newest tags 1.109.0-dev.2 / 1.108.0-rc.1; Tuesday cadence
means watch 11-03). OpenAI changelog ends 10-30 (gpt-6-rosalind),
Anthropic 10-30 (Opus 4.8 fast = shipped shield), OpenRouter blog-only
since 10-28, Ollama 0.40.13, Kong 3.9.4.

**Inward theme: prove parity, close the trace-visibility gap.** Guardrail
blocks already return 200 + denial content (Portkey's `soft_deny_200` is
daari's default) and MCP client-credentials upstream auth exists via
`secret://oauth` token refs — but it is undocumented; OTel spans export
tokens yet no cost or key/team identity; performance selection has no
latency objective; vLLM 0.33 upgrade notes missing.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 286 | Cost + key/team attributes on OTel GenAI spans | 3 | 2 | Portkey v2.32.0 Complete Logs export | Per-tenant cost traces in operator-owned OTel backend, no log pipeline | Filed [#2085](https://github.com/naveenreddyalka/daari/issues/2085) |
| 287 | Latency SLO bucketing for performance virtual-model selection | 3 | 2 | OpenRouter rebuilt provider routing | SLO sees local-tier latencies no cloud router can | Filed [#2086](https://github.com/naveenreddyalka/daari/issues/2086) |
| 288 | vLLM 0.33.0 GA upgrade notes (CUDA 13-only, image alias) | 2 | 1 | vLLM release notes | Honest local-tier upgrade story before operators hit it | Filed [#2087](https://github.com/naveenreddyalka/daari/issues/2087) |
| 289 | Document MCP client-credentials upstream via `secret://oauth` | 2 | 1 | Portkey v2.32.0 MCP OAuth config | Capability exists on-box; the recipe is the gap | Filed [#2088](https://github.com/naveenreddyalka/daari/issues/2088) |
| 290 | Integration fence for the 11-01/11-02 overnight wave | 2 | 2 | — (testability) | Hermetic proof: signals binding, PATCH, perf mode, fast shield | Filed [#2089](https://github.com/naveenreddyalka/daari/issues/2089) |
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
| 266–269 | Tenant signal binding; virtual_models PATCH; performance selection; Opus 4.8 fast shield | 3–4 | 1–3 | Portkey / LiteLLM / OpenRouter / Anthropic | Tenant levers + realized perf + deprecation shield on-box | Shipped (#2081–#2084) |
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
ask**); fleet-shared (Redis) EWMA state for performance selection (per-pod
in-process today by #2083 design — file on a multi-pod routing-skew ask);
LiteLLM Tuesday RC/stable (11-03) — compare refresh when it lands; Portkey
Codex PAT (`at-`) backend routing (niche); MCP SEP-3398 six-month release
cycle (next spec late March 2027 — docs date-pins only); OpenAI org
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
d1 Linux/Windows GA.

Verified fine this run — don't re-audit: **guardrail blocks already return
HTTP 200 with the denial as content** (`blocked_response`,
`daari/gateway/guardrails.py` — Portkey v2.32.0 `soft_deny_200` is daari's
default; never file); **MCP upstream client-credentials works today** via
`secret://oauth` token refs (`resolve_settings_secrets` walks
`mcp_servers[].token`; docs gap only = row 289); **stream-failure fallback
emits an error frame then a non-stream re-emit** (Portkey's
missing-terminal-event fix is covered); Claude Code pooled group budgets =
parity (`effective_caps`); Decisions facade at GA parity; ultrafast priced
6× (#1519); `list_amount` reconciled (#2063); LiteLLM GA floor 1.106.6;
IdP claim → team mapping exists; minute spend buckets stay scoped out;
**between_tools** not widened beyond Sonnet 5.5.

---

## Path to enterprise-grade — next 5 milestones

1. **Answer OpenRouter's performance router on-box** — selection shipped
   (268); latency SLO bucketing (287); compare copy (272); failover
   Grafana (274); fence it (290).
2. **Tenant-true observability** — span cost + key/team attrs (286);
   request tags (284) then tag attrs; team panels (rows 2020/2015 tail).
3. **Tenant governance dials** — signals binding shipped (266); tags
   (284); service-tier allowlist (277); priority header (275); TPD
   (271); then rows 62–67.
4. **Air-gap + jobs that finish loudly** — live offline ownership (282);
   doctor tip (285); Prom counter (279); batch webhooks (276) + org
   default (283); fences (270/280).
5. **Honesty/ops tail** — vLLM 0.33 notes (288); MCP client-credentials
   recipe (289); LiteLLM LTS (281) + 1.109 refresh (273); hot-reload (6).

---

## Changelog

- **2026-11-02 (trace cost; latency SLO; vLLM 0.33; MCP cc recipe)** —
  Marked rows 266–269 Shipped (#2081–#2084). Outward: vLLM 0.33.0 GA
  (CUDA 13-only artifacts, `vllm/vllm` alias); Portkey floor v2.32.0
  (MCP client-credentials, soft_deny_200, OTel cost/metadata attrs);
  LiteLLM/OpenAI/Anthropic/OpenRouter flat. Filed rows 286–290: OTel
  cost+tenant span attrs, latency SLO bucketing, vLLM 0.33 notes, MCP
  `secret://oauth` recipe, 11-01/02 wave fence. Verified parity: guardrail
  soft-deny-200 default; MCP cc capability; stream-fallback error frame.

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
