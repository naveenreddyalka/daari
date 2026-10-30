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

## Where daari stands (verified in-tree, 2026-10-29 pm)

**Loop velocity.** Morning signals/LFM3 board still open (247–250). Afternoon
merged the Portkey extra-labels ride-along and the llama.cpp guide (rows
240–241 Shipped). Open ride-along: LiteLLM-1.109 board (242–245), multimodal
LFM3 (246–247), signals operator surface (248–250), plus the P3 honesty tail.

**Outward.** **LiteLLM 1.108.0-rc.1** (10-29) is a parity patch onto the
1.106.x line — not a feature cut; stable floor stays **1.106.6 GA** (compare
doc still lags). **ngrok AI Gateway Virtual models** went GA (10-29): named
model → ordered failover list without client changes. OpenRouter same day:
private-provider CRUD (SaaS BYO-GPU — watch) + rebuilt default routing
cost/TTFT/reliability blend (narrative only). Flat since morning: Ollama
0.40.13, Portkey v2.31.0, Anthropic, Kong, vLLM 0.32.0, llama.cpp v0.8.0.

**Inward theme: finish the team-metrics operator surface, honest LiteLLM
floor, and a local virtual-model answer to ngrok.** `team_metrics` shipped
without Grafana panels, config-editor ownership, or a doctor tip when the
teams store is empty (every series collapses to `team="-"`). Compare doc
still pins an older GA floor. No operator-defined virtual model name →
ordered candidate list (only `:floor`/`:nitro` + pool frontier_fallback).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 251 | compare-litellm: GA floor 1.106.6; note 1.108.0-rc.1 | 2 | 1 | LiteLLM release notes | Honest floor; RC stays non-GA | Filed [#2019](https://github.com/naveenreddyalka/daari/issues/2019) |
| 252 | Grafana panels for team-labeled request/error rates | 2 | 1 | Portkey analytics / extra labels | Per-team traffic scraped on-box | Filed [#2020](https://github.com/naveenreddyalka/daari/issues/2020) |
| 253 | Config ownership + PATCH for `observability.team_metrics` | 3 | 1 | LiteLLM / Portkey control planes | Flip scrape cardinality live | Filed [#2021](https://github.com/naveenreddyalka/daari/issues/2021) |
| 254 | Doctor tip when `team_metrics` on but teams store empty | 2 | 1 | — (ops honesty) | Explain all-`team="-"` scrapes | Filed [#2022](https://github.com/naveenreddyalka/daari/issues/2022) |
| 255 | Named virtual models with ordered local/L6 failover | 4 | 3 | ngrok Virtual models GA | One client name; failover on-box | Filed [#2023](https://github.com/naveenreddyalka/daari/issues/2023) |
| 247 | LFM3 notes ride Ollama 0.40.13 (Linux/Windows GA, omni TTS) | 3 | 1 | Ollama release notes | Linux fleets get the local tier the copy denies | Filed [#2012](https://github.com/naveenreddyalka/daari/issues/2012) |
| 248 | Validate `signal_overrides` match keys + bucket values | 3 | 1 | Portkey Signals UI validation | Dead rules fail loud in on-box config | Filed [#2013](https://github.com/naveenreddyalka/daari/issues/2013) |
| 249 | Config ownership + PATCH for `routing.signal_overrides` | 3 | 2 | LiteLLM / Portkey control planes | Tune routing live, no cloud control plane | Filed [#2014](https://github.com/naveenreddyalka/daari/issues/2014) |
| 250 | Grafana panel for `daari_signal_override_total` by rule | 2 | 1 | Portkey analytics tab | Rule visibility scraped next to the router | Filed [#2015](https://github.com/naveenreddyalka/daari/issues/2015) |
| 242 | compare-litellm: 1.109.0-dev.1 watch; GA floor 1.106.6 | 2 | 1 | LiteLLM release notes | Honest prerelease bar; on-box stance clear | Filed [#2002](https://github.com/naveenreddyalka/daari/issues/2002) |
| 243 | Mid-stream fallback continuation after upstream death | 4 | 3 | LiteLLM 1.109 mid-stream fallback | Continue on next local/L6 hop; no SaaS proxy | Filed [#2003](https://github.com/naveenreddyalka/daari/issues/2003) |
| 244 | Opt-in `agent_access_default_deny` for multi_agent keys | 4 | 2 | LiteLLM `agent_access_default_deny` | Same trust floor as MCP grants, on-box | Shipped [#2004](https://github.com/naveenreddyalka/daari/issues/2004) |
| 245 | Optional `pricing_provider` / alias_of per model rates | 3 | 2 | LiteLLM `model_info.pricing_provider` | FinOps truth for aliases without cloud cost-map | Filed [#2005](https://github.com/naveenreddyalka/daari/issues/2005) |
| 246 | Optional `lfm3-vl` multimodal setup recipe + doctor tip | 3 | 2 | Ollama `ollama run lfm3-vl` | Vision agent turns stay local | Filed [#2006](https://github.com/naveenreddyalka/daari/issues/2006) |
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
| 19–28 | compact_to_fit / MCP fail-closed / 1.104 compare wave | 2–4 | 1–2 | LiteLLM | Shipped | Shipped |
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): **`LITELLM_OFFLINE_MODE` analog** (one switch for
outbound fetches — file after pricing alias lands); per-key/team-scoped
`signal_overrides` (after rows 248–249 prove out); `lfm3-omni` recipe / omni
routing matrix (after `lfm3-vl` row 246 merges); LiteLLM Admin Chat UI / Lens
(non-goal); llama.cpp `/v1/realtime` + `POST /tts` (pairs with row-8
Realtime/WS); llama.cpp deferred tools + `tool_reference`; Portkey
claim-based JWT; OpenRouter private-provider CRUD + S3/IAM destinations +
routing-cost narrative in compare-openrouter; OpenAI `/agents/automations`
passthrough; Prisma AIRS Agent Identity; Claude-on-GCP IAM egress (new dep —
human sign-off); Anthropic hosted `/v1/skills` proxy; Claude Tag beta
(non-goal); Open Responses WS; Anthropic OTel export beta; Prometheus
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate; Portkey WIF;
SCIM + multi-issuer SSO; Kong Skills/A2A; OpenRouter Private Endpoints L6
recipe; certifi emSign drop (still ships 2026.10.23); MCP SEP-3415 /
SEP-3392 / Skills-spec-to-beta links when merged; Ollama d1 Linux/Windows GA
(0.40.13 names LFM3 only); weighted virtual-model routing (after row 255).

Verified fine this run — don't re-audit: gzip already off-loop (LiteLLM
1.106.6 = daari #1710 parity); Portkey Signals classifier mode already feeds
overrides; Ollama facade `/api/version`; tts/asr platform-honest (recipe copy
is row 247); 10-28 wave self-fenced in gateway-flow; stream continuation is
row 243; MCP `require_key_access_defined` templates row 244; `pricing.models`
overrides work (alias is row 245); team Prom series unit-tested (#2017);
llama.cpp v0.8.0 guide landed (#2018); 1.108.0-rc.1 adds no new gateway
surface beyond the floor bump (row 251).

---

## Path to enterprise-grade — next 5 milestones

1. **Ride LiteLLM 1.109 where daari owns the levers** — floor/RC honesty
   (251 + 242), mid-stream continuation (243), agent grant deny (244),
   pricing alias (245), then the `LITELLM_OFFLINE_MODE` analog watch.
2. **Finish team-metrics as an operator surface** — Grafana (252), config
   ownership (253), empty-teams doctor (254); then signals 248–250.
3. **Answer ngrok Virtual models on-box** — named failover list (255);
   weighted / OpenRouter-routing narrative stay watch.
4. **Finish the Ollama 0.40.13 multimodal ride-along** — platform notes +
   omni TTS (247), `lfm3-vl` (246); omni recipe after.
5. **Finish tenancy, then demand-gated protocols** — rows 62–67, hot-reload
   (6); row 8 (Realtime closer via llama.cpp + Portkey GPT Live) + parked
   row 7; P3 honesty tail (225–226, 236, #1981, TTS/voices/skills).

---

## Changelog

- **2026-10-29 pm (team-metrics surface; ngrok virtual models; LiteLLM RC)** —
  Marked rows 240–241 Shipped (#2017/#2018). LiteLLM **1.108.0-rc.1** is a
  parity patch — filed row 251 (compare floor → 1.106.6). ngrok Virtual
  models GA → filed row 255 (ordered local/L6 failover). Filed rows 252–254
  finishing the team_metrics ship (Grafana, ownership, empty-teams doctor).
  OpenRouter private-providers + routing rebuild stay watch.

- **2026-10-29 (signals become an operator surface; LFM3 goes Linux)** —
  Marked rows 235/237–239 Shipped (#2008–#2011). Ollama **0.40.13** LFM3 on
  Linux/Windows — filed 247–250. LiteLLM GA floor → **1.106.6**. Killed
  Signals classifier-mode watch row.

- **2026-10-28 pm (ride LiteLLM 1.109-dev; finish LFM3 text path)** — Marked
  rows 233–234 Shipped. Filed rows 242–246 against v1.109.0-dev.1.

- **2026-10-28 (match Portkey v2.31.0, ride llama.cpp v0.8.0)** — Filed rows
  237–241.

- **2026-10-27 + pm → 08-28** — Condensed: Ollama 0.40.12 through this PRD's
  creation.
