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

## Where daari stands (verified in-tree, 2026-10-30 pm)

**Loop velocity.** Morning FinOps/air-gap board (#2030–#2034) is live and
labeled; LFM3 platform notes (#2012) merged on main — row 247 Shipped. The
LiteLLM-1.109 ride-along board remains fully merged (#2025–#2029).

**Outward.** **Ollama 0.40.13** is still the local-modality floor: LFM3 family
(text / VL / audio / **omni**) on Linux/Windows/macOS; `lfm3-omni` library card
is GA at ~2.2B (text+image+video+audio → text/speech). **OpenRouter** CSAM
in-flight screening (incl. ZDR retention carve-out) and Private Endpoints GA
are the cloud positioning delta — compare page still silent. **MCP SEP-3392**
classified `ext-skills` / `ext-tasks` as **Beta** (spec paths under
`specification/beta/`); daari MCP guide still frames Skills as SEP-2640-only.
LiteLLM still at **1.109.0-dev.2** (no stable 1.109); Portkey / Kong / vLLM
0.32.0 / llama.cpp b-builds flat vs morning scan. Anthropic Analytics API beta
unchanged (hour buckets + reconcile already filed).

**Inward theme: finish the LFM3 modality story and honesty surfaces.** Doctor
tips know `lfm3-omni` for speech, but there is no setup recipe and chat
`required_capabilities` never demands `audio`. LFM3-VL copy still says
"coming soon" for Linux after the text notes rode 0.40.13. Compare-openrouter
and MCP Beta docs lag the landscape. The 10-29/30 gateway wave still lacks an
integration fence.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 261 | `lfm3-omni` recipe + audio capability routing matrix | 4 | 2 | Ollama lfm3-omni / cloud multimodal | One on-box model replaces ASR+VLM+LLM+TTS hops | Filed [#2037](https://github.com/naveenreddyalka/daari/issues/2037) |
| 262 | compare-openrouter: CSAM screening + Private Endpoints | 2 | 1 | OpenRouter announcements | Honest on-box vs in-flight SaaS retention | Filed [#2038](https://github.com/naveenreddyalka/daari/issues/2038) |
| 263 | MCP SEP-3392 Beta lifecycle for skills/tasks docs | 2 | 1 | MCP extensions overview | Local skills/Tasks labeled at true maturity | Filed [#2039](https://github.com/naveenreddyalka/daari/issues/2039) |
| 264 | Finish LFM3-VL platform notes for Ollama 0.40.13 | 2 | 1 | Ollama release notes | Linux fleets get the vision L4 the copy denies | Filed [#2040](https://github.com/naveenreddyalka/daari/issues/2040) |
| 265 | Integration fence for 10-29/30 gateway wave | 2 | 2 | — (testability) | Hermetic proof mid-stream / agent deny / pricing / team | Filed [#2041](https://github.com/naveenreddyalka/daari/issues/2041) |
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
| 247 | LFM3 notes ride Ollama 0.40.13 (Linux/Windows GA, omni TTS) | 3 | 1 | Ollama release notes | Linux fleets get the local tier the copy denies | Shipped (#2012) |
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
| 24–28, 19–23 | Compact-to-fit + MCP grant fail-closed board | 2–4 | 1–2 | LiteLLM | Shipped | Shipped |
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): per-key/team-scoped `signal_overrides`
(after rows 248–249 prove out); minute-grain spend buckets (after row 256);
`list_amount` vs discounted `amount` in the ledger (after row 259); weighted
virtual-model routing (after row 255); **`lfm3-audio` setup recipe** (speech
wiring CLI — after omni recipe proves the pattern); OpenRouter Private
Endpoints L6 recipe (demand-gated; compare honesty first); llama.cpp
`/v1/realtime` + `POST /tts` (pairs with row-8 Realtime/WS); llama.cpp
deferred tools + `tool_reference`; Portkey claim-based JWT; OpenAI
`/agents/automations` passthrough + Agents `compaction`/`experimental`
fields; Prisma AIRS Agent Identity; Claude-on-GCP IAM egress (new dep —
human sign-off); Anthropic hosted `/v1/skills` proxy; Claude Tag beta
(non-goal); Open Responses WS; Anthropic OTel export beta; Prometheus
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate; Portkey WIF;
SCIM + multi-issuer SSO; Kong Skills/A2A; certifi emSign drop (still ships
2026.10.23); Ollama d1 Linux/Windows GA (0.40.13 names LFM3 only); LiteLLM
Admin Chat UI / Lens (non-goal).

Verified fine this run — don't re-audit: per-key-per-model RPM/TPM already in
settings; mid-stream continuation prefill-free by design; decision guardrails
local-only; LiteLLM v1.106.6 full release (row 251 finishes compare); Portkey
v2.31.0 floor; spend `group_by` covers 7 dims (bucket grain = row 256);
doctor TTS/ASR already recognizes `lfm3-omni` tags beside `lfm3-audio` (row
247); vLLM local-tier guide already cites 0.32.0 + `/v1/systemone`.

---

## Path to enterprise-grade — next 5 milestones

1. **Finish the LFM3 modality story on-box** — omni recipe + audio
   capability matrix (261); VL platform-note honesty (264); then
   `lfm3-audio` setup recipe (watch).
2. **FinOps truth against the provider bill** — hour buckets (256), ledger
   reconciliation vs Anthropic Analytics (259); then `list_amount` and
   minute buckets (watch).
3. **Air-gapped trust floor** — offline mode (260), body-cap honesty (257);
   image trust-store scrub tail rides along.
4. **Honesty vs cloud marketplaces** — OpenRouter CSAM/Private Endpoints
   compare (262); MCP Skills/Tasks Beta labeling (263); LiteLLM floor (251).
5. **Finish operator surfaces + tenancy** — team-metrics (252–254), signals
   (248–250), virtual models (255); rows 62–67 + hot-reload (6); fence the
   10-29/30 wave (265); row 8 + parked row 7 on demand.

---

## Changelog

- **2026-10-30 pm (LFM3 omni matrix; OpenRouter + MCP honesty)** — Marked
  row 247 Shipped (LFM3 platform notes on main). Filed rows 261–265: omni
  recipe + audio routing, compare-openrouter CSAM/Private Endpoints, MCP
  SEP-3392 Beta docs, LFM3-VL 0.40.13 note finish, 10-29/30 integration
  fence. Landscape: OpenRouter CSAM+Private Endpoints and MCP Skills/Tasks
  Beta are the outward deltas; LiteLLM still 1.109-dev.2.

- **2026-10-30 (FinOps truth; air-gapped floor; adopt the dead pm sibling)** —
  Marked rows 242–246 Shipped (#2025–#2029). Adopted rows 251–255. Anthropic
  Analytics + 128 MB Messages → rows 256–257, 259. LiteLLM offline-mode
  trigger → 260. `gpt-oss-safeguard` → 258. MCP SEP-3392 watch opened.

- **2026-10-29 pm (team-metrics surface; ngrok virtual models; LiteLLM RC)** —
  Marked rows 240–241 Shipped; filed 251–255. PRD PR failed pinned-rows
  test; rows adopted 10-30.

- **2026-10-29 (signals become an operator surface; LFM3 goes Linux)** —
  Marked 235/237–239 Shipped. Ollama 0.40.13 → filed 247–250. LiteLLM GA
  floor → 1.106.6.

- **2026-10-28 + pm → 08-28** — Condensed: Portkey v2.31.0, llama.cpp
  v0.8.0, LiteLLM 1.109-dev, finish-what-shipped through this PRD's creation.
