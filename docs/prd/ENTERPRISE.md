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

## Where daari stands (verified in-tree, 2026-10-31 pm)

**Loop velocity.** Morning board (rows 266–270) is live and unmerged; the
overnight wave (247–249, 251, 253, 255–257) stays Shipped. The deferred
10-30 pm PRD sibling finally landed on main after the morning PRD — content
aligned, pinned rows 19–28 intact.

**Outward.** LiteLLM **1.109.0-dev.2** (30 Oct): daily request **and token**
limits, provider/model RPM/TPM on project quotas, `x-litellm-priority`,
cosign under the rotated key, Anthropic `drop_params` drops `speed` after
fast-mode removals — compare page still stuck on dev.1 and still calls
mid-stream continuation a "next gap" though it shipped. OpenRouter's rebuilt
performance router (10-28) still has **zero** honesty copy on
`compare-openrouter.md` even though virtual models + the performance-aware
follow-on are the product answer. Anthropic 10-30 also: Models API reports
`capabilities.thinking.types.between_tools`; Compliance API returns saved
Instructions/Cowork prefs (Enterprise) — watch. Flat otherwise: Ollama
0.40.13, Portkey v2.31.0, Kong, vLLM 0.32.0, llama.cpp b12020 (no product
delta).

**Inward theme: close the 1.109/OpenRouter honesty gap and the day-grain
token dial.** Keys already have RPD but not TPD; admission priority is
key/team only (no request header); `daari_virtual_model_failover_total`
ships without a Grafana panel; compare pages lag the competitive claims
already driving rows 268 / mid-stream.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
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
| 261 | `lfm3-omni` recipe + audio capability routing matrix | 4 | 2 | Ollama lfm3-omni / cloud multimodal | One on-box model replaces ASR+VLM+LLM+TTS hops | Filed [#2037](https://github.com/naveenreddyalka/daari/issues/2037) |
| 262 | compare-openrouter: CSAM screening + Private Endpoints | 2 | 1 | OpenRouter announcements | Honest on-box vs in-flight SaaS retention | Filed [#2038](https://github.com/naveenreddyalka/daari/issues/2038) |
| 263 | MCP SEP-3392 Beta lifecycle for skills/tasks docs | 2 | 1 | MCP extensions overview | Local skills/Tasks labeled at true maturity | Filed [#2039](https://github.com/naveenreddyalka/daari/issues/2039) |
| 264 | Finish LFM3-VL platform notes for Ollama 0.40.13 | 2 | 1 | Ollama release notes | Linux fleets get the vision L4 the copy denies | Filed [#2040](https://github.com/naveenreddyalka/daari/issues/2040) |
| 265 | Integration fence for 10-29/30 gateway wave | 2 | 2 | — (testability) | Hermetic proof mid-stream / agent deny / pricing / team | Filed [#2041](https://github.com/naveenreddyalka/daari/issues/2041) |
| 258 | `gpt-oss-safeguard` recipe for decision guardrails | 3 | 2 | OpenRouter in-flight screening / Portkey cloud guardrails | Bring-your-own-policy moderation fully on-box, Apache 2.0 | Filed [#2032](https://github.com/naveenreddyalka/daari/issues/2032) |
| 259 | Reconcile ledger vs Anthropic Analytics API | 4 | 3 | Anthropic console / LiteLLM spend tabs | Ledger of record stays on-box; pull proves it against the bill | Filed [#2033](https://github.com/naveenreddyalka/daari/issues/2033) |
| 260 | `security.offline_mode`: fail-closed off-box egress switch | 3 | 2 | LiteLLM `LITELLM_OFFLINE_MODE` | Air-gapped is home turf; guarantee, not audit | Filed [#2034](https://github.com/naveenreddyalka/daari/issues/2034) |
| 256–257 | Hour spend buckets; body-cap doctor honesty | 2–3 | 1 | Anthropic Analytics / — | Hour-grain FinOps + cap honesty on-box | Shipped (#2048/#2049) |
| 251 | compare-litellm: GA floor 1.106.6; note 1.108.0-rc.1 | 2 | 1 | LiteLLM release notes | Honest floor; v1.106.6 now a full release | Shipped (#2045) |
| 252 | Grafana panels for team-labeled request/error rates | 2 | 1 | Portkey analytics / extra labels | Per-team traffic scraped on-box | Filed [#2020](https://github.com/naveenreddyalka/daari/issues/2020) |
| 253 | Config ownership + PATCH for `observability.team_metrics` | 3 | 1 | LiteLLM / Portkey control planes | Flip scrape cardinality live | Shipped (#2046) |
| 254 | Doctor tip when `team_metrics` on but teams store empty | 2 | 1 | — (ops honesty) | Explain all-`team="-"` scrapes | Filed [#2022](https://github.com/naveenreddyalka/daari/issues/2022) |
| 255 | Named virtual models with ordered local/L6 failover | 4 | 3 | ngrok Virtual models GA | One client name; failover on-box | Shipped (#2047) |
| 247 | LFM3 notes ride Ollama 0.40.13 (Linux/Windows GA, omni TTS) | 3 | 1 | Ollama release notes | Linux fleets get the local tier the copy denies | Shipped (#2036) |
| 248–249 | `signal_overrides` validation; ownership + PATCH | 3 | 1–2 | Portkey Signals / control planes | Dead rules fail loud; tune live on-box | Shipped (#2043/#2044) |
| 250 | Grafana panel for `daari_signal_override_total` by rule | 2 | 1 | Portkey analytics tab | Rule visibility scraped next to the router | Filed [#2015](https://github.com/naveenreddyalka/daari/issues/2015) |
| 242–246 | LiteLLM-1.109 ride-along (compare, mid-stream continue, agent deny, pricing alias, `lfm3-vl`) | 2–4 | 1–3 | LiteLLM 1.109 / Ollama | Continue on next local hop; FinOps truth; vision local | Shipped (#2025–#2029) |
| 237–239 | Portkey denial / MCP timeout / request-fact signals | 3–4 | 1–3 | Portkey v2.31.0 / Signals | Operator-owned on-box | Shipped (#2009–#2011) |
| 240 | Opt-in `team` label on requests/errors Prom series | 3 | 2 | Portkey `PROMETHEUS_EXTRA_LABELS` | Per-team traffic scraped on-box | Shipped (#2017) |
| 241 | llama.cpp v0.8.0 local-tier guide + landscape refresh | 2 | 1 | llama.cpp release notes | Linux path to LFM3/d1 today | Shipped (#2018) |
| 233–235 | LFM3 L3 recipe, unused d1/lfm3 doctor, `lfm3-audio` | 3 | 1–2 | Ollama / Phonon | Local speech + agent tier | Shipped (#2000/#2001/#2008) |
| 236 | Prometheus + stats for decisions L0 cache hits | 2 | 1 | LiteLLM spend / cache tabs | Local judgment reuse scrapeable | Filed [#1987](https://github.com/naveenreddyalka/daari/issues/1987) |
| 225 | `daari_schema_ok` HELP + Grafana cover Postgres skew | 2 | 1 | — (ops honesty) | Gauge right; text lagged | Filed [#1966](https://github.com/naveenreddyalka/daari/issues/1966) |
| 226 | Prometheus counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform metrics | Local scrape next to TTS | Filed [#1967](https://github.com/naveenreddyalka/daari/issues/1967) |
| 227–232 | 10-27 wave (Helm at-rest, sealed stores, SEP-2640, fence, d1) | 2–4 | 1–2 | LiteLLM / OpenAI / MCP SDK | Sealed payloads + on-box skills | Shipped (231 Prom → #1981) |
| 217–224 | 10-26 waves (leases, at-rest, webhooks, Terra, reports, skills) | 2–4 | 1–3 | OpenAI / LiteLLM / Bloomberg | HA jobs, EKM analog, FinOps | Shipped |
| 198–216 | 10-24/25 trust/FinOps/voice waves | 2–4 | 1–3 | LiteLLM / Anthropic / OpenAI | Trust floor, push, local voice | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | Shipped | Shipped |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | Shipped | Shipped |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | Shipped | Shipped |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | Shipped | Shipped |
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | Shipped | Shipped |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | Shipped | Shipped |
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): minute-grain spend buckets (**deliberately
scoped out in the hour-bucket work — row-blowup; only on an explicit FinOps
ask**); `list_amount` vs discounted `amount` in the ledger (after row 259);
weighted/latency SLO knobs on virtual-model selection (after row 268);
`lfm3-audio` setup recipe (after row 261 proves the pattern); OpenAI org
**external key management** (SDK 10-31 — pair with the at-rest EKM analog
when the Management API shape stabilizes beyond feature-flag); Anthropic
Compliance API user-preferences export (Enterprise Instructions/Cowork —
pair with erasure); Models API `between_tools` matrix refresh if Anthropic
widens beyond Sonnet 5.5; `gpt-6-rosalind` catalog entry (trusted-access
research only; price when GA); Claude Code gateway-upstream `groups` /
`guardrail_trace` passthrough (2.1.314 — IdP claim→team mapping already
in-tree); MCP SEP-3392 docs-link refresh when extension repos rename (row
263 covers the Beta label); OpenRouter private-provider CRUD + S3/IAM
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

Verified fine this run — don't re-audit: IdP claim → team mapping already
exists (`sso_keys.py`); minute spend buckets stay scoped out; mid-stream
fallback continuation is **shipped** (row 242–246) — compare-litellm text
lagged; `daari_virtual_model_failover_total` counter shipped (Grafana is
the remaining gap — row 274); doctor validates virtual-model candidate ids;
signal-rule validation enforces `SIGNAL_KEYS` + context buckets; Portkey
changelog cache flake — v2.31.0 stays the floor; LiteLLM GA floor 1.106.6
in-tree; RPD/RPM/TPM already cover request and minute grains (TPD is the
day-token hole — row 271).

---

## Path to enterprise-grade — next 5 milestones

1. **Answer OpenRouter's performance router on-box** — virtual models (255
   Shipped); performance-aware selection (268), live edit (267), fence
   (270); compare honesty now splits CSAM/private (262) and performance-
   router copy (272).
2. **Tenant-aware routing + admission** — per-key/team signals (266);
   request priority header (275); then rows 62–67.
3. **FinOps truth + day-grain token dial** — Anthropic Analytics reconcile
   (259); TPD next to RPD (271); `list_amount` (watch); hour buckets
   shipped (256).
4. **Deprecation shield + air-gapped trust floor** — Opus 4.8 fast removal
   (269), offline mode (260), `gpt-oss-safeguard` (258).
5. **Local modality + honesty/ops tail** — `lfm3-omni` (261), LFM3-VL
   (264), MCP Beta (263); compare-litellm 1.109.0-dev.2 refresh (273);
   virtual-model Grafana (274); hot-reload (6); P3 tail (225–226, 236,
   250, 252, 254, fences 265/270).

---

## Changelog

- **2026-10-31 pm (1.109/OpenRouter honesty; TPD; request priority)** —
  Morning rows 266–270 stay Filed. Outward: LiteLLM 1.109.0-dev.2 daily
  token limits + priority header; OpenRouter performance-router still
  absent from compare-openrouter; compare-litellm mid-stream claim stale.
  Filed rows 271–275: TPD quotas, OpenRouter performance-router honesty,
  LiteLLM 1.109.0-dev.2 compare refresh, virtual-model failover Grafana,
  `X-Daari-Priority` admission header. Watch adds Anthropic Compliance
  user-preferences + Models API `between_tools` widen.

- **2026-10-31 (performance-aware routing; tenant signals; deprecation
  shield)** — Marked rows 247–249, 251, 253, 255–257 Shipped (#2036,
  #2043–#2049 — seven merges overnight). Adopted the 10-30 pm Actions
  sibling's rows 261–265 (its PRD PR #2042 died on the pinned-rows test —
  sixth death; issues #2037–#2041 live; PR later merged aligned). Outward:
  OpenRouter's rebuilt performance router (10-28 blog) and Anthropic's
  Opus 4.8 fast-mode removal (11-30) — filed rows 266–270. Verified IdP
  claim→team mapping already in-tree; minute buckets stay scoped out.

- **2026-10-30 (FinOps truth; air-gapped floor; adopt the dead pm sibling)** —
  Marked rows 242–246 Shipped (#2025–#2029). Adopted 10-29 pm rows
  251–255. Filed 256–260. MCP SEP-3392 watch.

- **2026-10-29 pm → 10-28** — Condensed: team-metrics / virtual models /
  signals / LFM3 Linux / Portkey v2.31.0 / llama.cpp v0.8.0 through
  Apache 2.0 and this PRD's creation.
