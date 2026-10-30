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

## Where daari stands (verified in-tree, 2026-10-30)

**Loop velocity.** The whole LiteLLM-1.109 ride-along board merged within two
days of filing: compare watch (#2025), mid-stream fallback continuation
(#2026), agent grant deny (#2027), pricing alias (#2028), `lfm3-vl` recipe
(#2029) — rows 242–246 Shipped, plus team Prom label (#2017) and the
llama.cpp guide (#2018). The 10-29 pm Actions sibling's PRD PR died on the
pinned-rows test (fifth such death); its rows 251–255 and issues are adopted
below — the issues themselves are live and labeled.

**Outward.** **Anthropic** is the delta: 10-28 raised first-party
Messages/Token-Counting request caps **32 → 128 MB**; 10-29 launched the
**Usage and Cost Analytics API** beta (minute/hour/day buckets, 5 group dims
incl. actor, `amount` vs `list_amount`) and legacy-ized the old usage/cost
reports. **LiteLLM v1.106.6 is now a full (non-prerelease) GitHub release**
— row 251's floor bump is vindicated; 1.109.0-dev.2 (10-30) adds
per-provider/per-model project quotas and prefill-free mid-stream fallback,
both already matched in-tree (see verified-fine). **MCP SEP-3392 (Extension
Lifecycle) merged 10-29**: `ext-skills` / `ext-tasks` classified **Beta**.
OpenRouter 10-29: private-provider CRUD + announced in-flight CSAM screening
of all inference — a strong daari on-box positioning contrast. Flat: Ollama
0.40.13, Portkey v2.31.0, Kong, vLLM 0.32.0, llama.cpp b-builds.

**Inward theme: FinOps truth and the air-gapped trust floor.** daari's spend
report buckets stop at day|month while Anthropic's new analytics shape does
hours; nothing reconciles the ledger against the provider bill; the default
10 MiB body cap now binds ~13× below Anthropic's 128 MB with no doctor
honesty; no single switch asserts zero off-box egress for air-gapped estates
(LiteLLM 1.109-dev ships `LITELLM_OFFLINE_MODE`); and decision guardrails
never point operators at `gpt-oss-safeguard` for on-box bring-your-own-policy
moderation.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 256 | Hour bucket on spend report rollups | 3 | 1 | Anthropic Analytics API (1m/1h/1d) | Hour-grain FinOps off local ledger, no SaaS plane | Filed [#2030](https://github.com/naveenreddyalka/daari/issues/2030) |
| 257 | Doctor honesty: body cap vs Anthropic 128 MB Messages | 2 | 1 | — (ops honesty) | Operator owns the RAM-vs-cap trade-off, told when it binds | Filed [#2031](https://github.com/naveenreddyalka/daari/issues/2031) |
| 258 | `gpt-oss-safeguard` recipe for decision guardrails | 3 | 2 | OpenRouter in-flight screening / Portkey cloud guardrails | Bring-your-own-policy moderation fully on-box, Apache 2.0 | Filed [#2032](https://github.com/naveenreddyalka/daari/issues/2032) |
| 259 | Reconcile ledger vs Anthropic Analytics API | 4 | 3 | Anthropic console / LiteLLM spend tabs | Ledger of record stays on-box; pull proves it against the bill | Filed [#2033](https://github.com/naveenreddyalka/daari/issues/2033) |
| 260 | `security.offline_mode`: fail-closed off-box egress switch | 3 | 2 | LiteLLM `LITELLM_OFFLINE_MODE` | Air-gapped is home turf; guarantee, not audit | Filed [#2034](https://github.com/naveenreddyalka/daari/issues/2034) |
| 251 | compare-litellm: GA floor 1.106.6; note 1.108.0-rc.1 | 2 | 1 | LiteLLM release notes | Honest floor; v1.106.6 now a full release | Filed [#2019](https://github.com/naveenreddyalka/daari/issues/2019) |
| 252 | Grafana panels for team-labeled request/error rates | 2 | 1 | Portkey analytics / extra labels | Per-team traffic scraped on-box | Filed [#2020](https://github.com/naveenreddyalka/daari/issues/2020) |
| 253 | Config ownership + PATCH for `observability.team_metrics` | 3 | 1 | LiteLLM / Portkey control planes | Flip scrape cardinality live | Filed [#2021](https://github.com/naveenreddyalka/daari/issues/2021) |
| 254 | Doctor tip when `team_metrics` on but teams store empty | 2 | 1 | — (ops honesty) | Explain all-`team="-"` scrapes | Filed [#2022](https://github.com/naveenreddyalka/daari/issues/2022) |
| 255 | Named virtual models with ordered local/L6 failover | 4 | 3 | ngrok Virtual models GA | One client name; failover on-box | Filed [#2023](https://github.com/naveenreddyalka/daari/issues/2023) |
| 247 | LFM3 notes ride Ollama 0.40.13 (Linux/Windows GA, omni TTS) | 3 | 1 | Ollama release notes | Linux fleets get the local tier the copy denies | Filed [#2012](https://github.com/naveenreddyalka/daari/issues/2012) |
| 248 | Validate `signal_overrides` match keys + bucket values | 3 | 1 | Portkey Signals UI validation | Dead rules fail loud in on-box config | Filed [#2013](https://github.com/naveenreddyalka/daari/issues/2013) |
| 249 | Config ownership + PATCH for `routing.signal_overrides` | 3 | 2 | LiteLLM / Portkey control planes | Tune routing live, no cloud control plane | Filed [#2014](https://github.com/naveenreddyalka/daari/issues/2014) |
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

Watch rows (do not file yet): **`lfm3-omni` recipe / omni routing matrix**
(trigger fired — `lfm3-vl` merged 10-30; file next run); per-key/team-scoped
`signal_overrides` (after rows 248–249 prove out); minute-grain spend buckets
(after row 256); `list_amount` vs discounted `amount` in the ledger (after
row 259); weighted virtual-model routing (after row 255); **MCP SEP-3392
Extension Lifecycle merged 10-29** — `ext-skills`/`ext-tasks` now Beta;
update daari skills/Tasks docs + links when the extension repos rename;
OpenRouter in-flight CSAM screening (compare-openrouter positioning note:
daari guardrails run on-box); OpenRouter private-provider CRUD + S3/IAM
destinations + routing-cost narrative; LiteLLM Admin Chat UI / Lens
(non-goal); llama.cpp `/v1/realtime` + `POST /tts` (pairs with row-8
Realtime/WS); llama.cpp deferred tools + `tool_reference`; Portkey
claim-based JWT; OpenAI `/agents/automations` passthrough + Agents
`compaction`/`experimental` fields; Prisma AIRS Agent Identity;
Claude-on-GCP IAM egress (new dep — human sign-off); Anthropic hosted
`/v1/skills` proxy; Claude Tag beta (non-goal); Open Responses WS; Anthropic
OTel export beta; Prometheus exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG /
OAuth-delegate; Portkey WIF; SCIM + multi-issuer SSO; Kong Skills/A2A;
OpenRouter Private Endpoints L6 recipe; certifi emSign drop (still ships
2026.10.23); Ollama d1 Linux/Windows GA (0.40.13 names LFM3 only).

Verified fine this run — don't re-audit: per-key-per-model RPM/TPM already in
settings (`model_rpm`/`model_tpm` + per-model-id overrides) — LiteLLM
1.109-dev.2 `enforce_project_model_quota` parity exists; mid-stream
continuation is **prefill-free by design** (`_with_stream_continuation`
appends the assistant partial + a user continue turn), matching LiteLLM
dev.2's no-prefill fix; decision guardrails already reject frontier models
(local-only enforced); **LiteLLM v1.106.6 is a full non-prerelease GitHub
release** (row 251 vindicated; the compare PR that merged 10-29 kept 1.106.5
— the open issue finishes it); Portkey's public changelog page intermittently
serves a stale v2.20.0 cache — v2.31.0 stays the verified floor; spend
`group_by` covers 7 dims incl. `service_tier`/`user` (bucket grain is the
only analytics gap, row 256).

---

## Path to enterprise-grade — next 5 milestones

1. **FinOps truth against the provider bill** — hour buckets (row 256),
   ledger reconciliation vs Anthropic Analytics (259); then `list_amount`
   and minute buckets (watch).
2. **Air-gapped trust floor** — offline mode switch (260), body-cap honesty
   (257); image trust-store scrub tail (#1929) rides along.
3. **Finish the operator surfaces that shipped half-done** — team-metrics
   (252–254), signals (248–250), LiteLLM floor honesty (251).
4. **Answer ngrok Virtual models and cloud moderation on-box** — named
   failover list (255), `gpt-oss-safeguard` guardrail recipe (258); LFM3
   platform notes (247) + `lfm3-omni` recipe next run.
5. **Finish tenancy, then demand-gated protocols** — rows 62–67, hot-reload
   (6); row 8 + parked row 7; P3 honesty tail (225–226, 236, #1981,
   TTS/voices/skills).

---

## Changelog

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
