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

## Where daari stands (verified in-tree, 2026-10-31)

**Loop velocity.** Seven of yesterday's board merged overnight: signal-rule
validation (#2043), ownership + PATCH for `signal_overrides` (#2044) and
`team_metrics` (#2046), the LiteLLM 1.106.6 compare floor (#2045), **named
virtual models with ordered failover (#2047)**, hour spend buckets (#2048),
and the body-cap doctor tip (#2049) — rows 247–249, 251, 253, 255–257
Shipped. The 10-30 pm Actions sibling's PRD PR died on the pinned-rows test
(sixth death — it condensed rows 19–28); its rows 261–265 and issues
#2037–#2041 are live and adopted below.

**Outward.** **Anthropic 10-30: fast mode for Claude Opus 4.8 is deprecated,
removal 2026-11-30** — `speed: "fast"` with `claude-opus-4-8` will hard-error
after that; migrate to Opus 5.5. **OpenRouter published its rebuilt provider
routing** (10-28 blog): the default router now scores every endpoint on
realized price/latency/throughput/error-rate in real time (−16.9% TTFT,
−46% capacity errors, +6% cost) — the sharpest competitive claim yet against
static ordered failover. OpenAI 10-30: `gpt-6-rosalind` (trusted-access
research only); 10-31 SDKs add org **external key management**, agent
compaction/review settings, SIP DTMF. Flat: LiteLLM 1.109.0-dev.2 (GA floor
1.106.6), Ollama 0.40.13, Portkey v2.31.0, Kong, vLLM 0.32.0.

**Inward theme: make routing tenant-aware and performance-aware, and shield
deprecations.** `signal_overrides` are global-only — no per-key/team binding
even though keys/teams already carry budgets, guardrails, and region pins;
`routing.virtual_models` is missing from the ownership/PATCH allowlist the
day after it shipped; virtual-model failover is strict-order with no realized
latency/error awareness (OpenRouter's new router is the foil); and the model
lifecycle calendar is model-level and OpenAI-only, so the Opus 4.8 fast-mode
removal — a model+speed-scoped deprecation — cannot be expressed, warned
about, or shielded.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
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
compare-openrouter note on the rebuilt performance router (after row 262
merges; row 268 is the product answer); weighted/latency SLO knobs on
virtual-model selection (after row 268); `lfm3-audio` setup recipe (after
row 261 proves the pattern); OpenAI org **external key management** (SDK
10-31 — pair with the at-rest EKM analog when the API shape stabilizes);
`gpt-6-rosalind` catalog entry (trusted-access research only; price when
GA); Claude Code gateway-upstream `groups` / `guardrail_trace` passthrough
(2.1.314 — IdP claim→team mapping already in-tree); MCP SEP-3392 docs-link
refresh when extension repos rename (row 263 covers the Beta label);
OpenRouter private-provider CRUD + S3/IAM destinations; LiteLLM Admin Chat
UI / Lens (non-goal); llama.cpp `/v1/realtime` + `POST /tts` (pairs with
row-8 Realtime/WS); llama.cpp deferred tools + `tool_reference`; Portkey
claim-based JWT; OpenAI `/agents/automations` passthrough + Agents
`compaction`/`experimental`/session-review fields; Prisma AIRS Agent
Identity; Claude-on-GCP IAM egress (new dep — human sign-off); Anthropic
hosted `/v1/skills` proxy; Claude Tag beta (non-goal); Open Responses WS;
Anthropic OTel export beta; Prometheus exemplars + `gen_ai.agent.*`;
LiteLLM ID-JAG / OAuth-delegate; Portkey WIF; SCIM + multi-issuer SSO;
Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign
drop (still ships 2026.10.23); Ollama d1 Linux/Windows GA.

Verified fine this run — don't re-audit: IdP claim → team mapping already
exists (`sso_keys.py`: `mapping_claim` values resolve to a key policy whose
team membership re-syncs on mint/refresh) — Claude Code's new gateway
`groups` knob needs no daari-side tenancy work; minute spend buckets were
**scoped out on purpose** in the hour-bucket change (docstring says row
blowup) — do not file; `daari_virtual_model_failover_total` counter shipped
with the failover work; doctor validates virtual-model candidate ids and
empty lists; signal-rule validation enforces `SIGNAL_KEYS` + context
buckets (shipped); Portkey's public changelog page intermittently serves a
stale v2.20.0 cache — v2.31.0 stays the verified floor; LiteLLM GA floor
1.106.6 is now in-tree (compare page merged).

---

## Path to enterprise-grade — next 5 milestones

1. **Answer OpenRouter's performance router on-box** — virtual models now
   exist (255 Shipped); make selection performance-aware (268), editable
   live (267), and fenced (270); compare honesty rides row 262.
2. **Tenant-aware routing** — per-key/team `signal_overrides` binding (266)
   on top of the shipped validation/ownership (248–249); then rows 62–67
   (end-user inventory, guardrail profiles, paginated rollups).
3. **FinOps truth against the provider bill** — ledger reconciliation vs
   Anthropic Analytics (259); hour buckets shipped (256); then
   `list_amount` (watch).
4. **Deprecation shield + air-gapped trust floor** — Opus 4.8 fast removal
   (269), offline mode switch (260), `gpt-oss-safeguard` recipe (258);
   image trust-store scrub tail (#1929) rides along.
5. **Local modality story + honesty tail** — `lfm3-omni` recipe (261),
   LFM3-VL notes (264), MCP Beta labels (263); hot-reload (6); P3 tail
   (225–226, 236, 250, 252, 254, fences 265/270).

---

## Changelog

- **2026-10-31 (performance-aware routing; tenant signals; deprecation
  shield)** — Marked rows 247–249, 251, 253, 255–257 Shipped (#2036,
  #2043–#2049 — seven merges overnight). Adopted the 10-30 pm Actions
  sibling's rows 261–265 (its PRD PR #2042 died on the pinned-rows test —
  sixth death; issues #2037–#2041 live). Outward: OpenRouter's rebuilt
  performance router (10-28 blog) and Anthropic's Opus 4.8 fast-mode
  removal (11-30) — filed rows 266–270: per-key/team signal binding,
  virtual-model ownership/PATCH, performance-aware candidate selection,
  speed-scoped lifecycle shield, and the overnight-wave fence. Verified
  IdP claim→team mapping already in-tree; minute buckets stay scoped out.

- **2026-10-30 (FinOps truth; air-gapped floor; adopt the dead pm sibling)** —
  Marked rows 242–246 Shipped (#2025–#2029, whole LiteLLM-1.109 board merged
  within two days). Adopted the 10-29 pm Actions sibling's rows 251–255 (its
  PRD PR died on the pinned-rows test — fifth death; issues live). Anthropic
  10-28/29: Messages cap → 128 MB, Usage/Cost Analytics API beta — filed
  rows 256–257 and 259. LiteLLM v1.106.6 confirmed a full release; 1.109-dev
  `LITELLM_OFFLINE_MODE` trigger fired (pricing alias landed) — filed row
  260. Filed row 258 (`gpt-oss-safeguard` on-box moderation vs OpenRouter's
  new in-flight screening). MCP SEP-3392 merged (skills/tasks Beta — watch).

- **2026-10-29 pm (team-metrics surface; ngrok virtual models; LiteLLM RC)** —
  Actions sibling run: marked rows 240–241 Shipped (#2017/#2018); filed rows
  251–255 (compare floor, team-metrics Grafana/ownership/doctor, named
  virtual-model failover vs ngrok GA). Its PRD PR failed the pinned-rows
  test; rows adopted 10-30.

- **2026-10-29 (signals become an operator surface; LFM3 goes Linux)** —
  Marked rows 235/237–239 Shipped (#2008–#2011). Ollama **0.40.13** LFM3 on
  Linux/Windows — filed 247–250. LiteLLM GA floor → **1.106.6**. Killed
  Signals classifier-mode watch row.

- **2026-10-28 + pm (Portkey v2.31.0; llama.cpp v0.8.0; LiteLLM 1.109-dev)** —
  Marked rows 233–234 Shipped. Filed rows 237–246.

- **2026-10-27 + pm → 08-28** — Condensed: finish-what-shipped, Ollama
  0.40.12, leases/at-rest/Terra through Apache 2.0 and this PRD's creation.
