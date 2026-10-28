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

## Where daari stands (verified in-tree, 2026-10-28 pm)

**Loop velocity.** Morning Portkey/llama.cpp board still open (rows 237–241).
LFM3 L3 recipe + unused d1/lfm3 doctor tip shipped same day (PRs #2000 /
#2001 → rows 233–234). Open ride-along is now `lfm3-audio` (235),
`lfm3-vl` (246), Linux llama.cpp guide (241), plus the P3 honesty tail.

**Outward.** **LiteLLM v1.109.0-dev.1** (10-28, prerelease; 700+ PRs) is the
real delta since morning: mid-stream fallback continuation, `LITELLM_OFFLINE_MODE`,
`agent_access_default_deny`, `model_info.pricing_provider`, Admin Chat UI.
GA floor stays **1.106.5**. Unchanged: llama.cpp v0.8.0 (realtime + `/tts`,
LFM3/d1 on Linux), Ollama 0.40.12 Apple-only LFM3/d1, Portkey/Prisma AIRS
v2.31.0 Signals/custom denials/MCP timeouts/Prom workspace label. OpenAI
Agents **scheduled automations** (`/v1/agents/automations`, 10-23) and
Anthropic API version `2026-10-21` stay demand/watch. Flat: Kong, vLLM
0.32.0, OpenRouter S3 IAM destinations (watch).

**Inward theme: ride LiteLLM 1.109 where daari already owns the levers.**
Stream path keeps partials (#973) but does not continue mid-answer on the
next tier; MCP fail-closed exists but multi_agent has no grant analog;
`pricing.models` cannot alias another catalog row; compare-litellm stops at
1.106/1.107. Vision LFM3 has no setup recipe beside text L3.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 242 | compare-litellm: 1.109.0-dev.1 watch; GA floor 1.106.5 | 2 | 1 | LiteLLM release notes | Honest prerelease bar; on-box stance clear | Filed [#2002](https://github.com/naveenreddyalka/daari/issues/2002) |
| 243 | Mid-stream fallback continuation after upstream death | 4 | 3 | LiteLLM 1.109 mid-stream fallback | Continue on next local/L6 hop; no SaaS proxy | Filed [#2003](https://github.com/naveenreddyalka/daari/issues/2003) |
| 244 | Opt-in `agent_access_default_deny` for multi_agent keys | 4 | 2 | LiteLLM `agent_access_default_deny` | Same trust floor as MCP grants, on-box | Filed [#2004](https://github.com/naveenreddyalka/daari/issues/2004) |
| 245 | Optional `pricing_provider` / alias_of per model rates | 3 | 2 | LiteLLM `model_info.pricing_provider` | FinOps truth for aliases without cloud cost-map | Filed [#2005](https://github.com/naveenreddyalka/daari/issues/2005) |
| 246 | Optional `lfm3-vl` multimodal setup recipe + doctor tip | 3 | 2 | Ollama `ollama run lfm3-vl` | Vision agent turns stay local | Filed [#2006](https://github.com/naveenreddyalka/daari/issues/2006) |
| 237 | Per-rule custom guardrail denial messages | 3 | 1 | Portkey v2.31.0 custom errors | Operator-owned denial copy, on-box | Filed [#1994](https://github.com/naveenreddyalka/daari/issues/1994) |
| 238 | Per-server MCP egress request timeout | 3 | 1 | Portkey per-integration timeouts | Tune each local hop; honest breakers | Filed [#1995](https://github.com/naveenreddyalka/daari/issues/1995) |
| 239 | Request-fact signals in `daari_meta` + opt-in overrides | 4 | 3 | Portkey Signals beta | Facts already free on-box | Filed [#1996](https://github.com/naveenreddyalka/daari/issues/1996) |
| 240 | Opt-in `team` label on requests/errors Prom series | 3 | 2 | Portkey `PROMETHEUS_EXTRA_LABELS` | Per-team traffic scraped on-box | Filed [#1997](https://github.com/naveenreddyalka/daari/issues/1997) |
| 241 | llama.cpp v0.8.0 local-tier guide + landscape refresh | 2 | 1 | llama.cpp release notes | Linux path to LFM3/d1 today | Filed [#1998](https://github.com/naveenreddyalka/daari/issues/1998) |
| 233 | Optional LFM3 L3 setup recipe (256K local agent tier) | 3 | 2 | Ollama `ollama run lfm3` | One setup prompt, on-box | Shipped (#2000) |
| 234 | Doctor tip when Ollama serves d1/lfm3 but unused | 3 | 1 | — (ops honesty) | Point at local win before L6 | Shipped (#2001) |
| 235 | Recognize `lfm3-audio` as local ASR/TTS beside Phonon | 3 | 2 | Ollama speech / Phonon | 18-language local speech | Filed [#1986](https://github.com/naveenreddyalka/daari/issues/1986) |
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

Watch rows (do not file yet): **`LITELLM_OFFLINE_MODE` analog** (one switch for
outbound fetches — file after pricing alias lands); LiteLLM Admin Chat UI /
Lens (non-goal); llama.cpp `/v1/realtime` + `POST /tts` (pairs with row-8
Realtime/WS); llama.cpp deferred tools + `tool_reference`; Portkey Signals
classifier mode (after row 239); Portkey claim-based JWT; OpenRouter S3/IAM
destinations; OpenAI `/agents/automations` passthrough; Prisma AIRS Agent
Identity; Claude-on-GCP IAM egress (new dep — human sign-off); Anthropic
hosted `/v1/skills` proxy; Claude Tag beta (non-goal); Open Responses WS;
Anthropic OTel export beta; Prometheus exemplars + `gen_ai.agent.*`; LiteLLM
ID-JAG / OAuth-delegate; Portkey WIF; SCIM + multi-issuer SSO; Kong Skills/A2A;
OpenRouter Private Endpoints L6 recipe; certifi emSign drop; llama.cpp `mtmd`;
Ollama LFM3/d1 Linux/Windows GA; MCP SEP-3415 / SEP-3392 when merged.

Verified fine this run — don't re-audit: LFM3 text recipe + unused tip in-tree
(#2000/#2001); Portkey-parity gaps still accurately rows 237–241; d1 catalog +
SEP-2640 + sealed stores + Helm key knobs merged; stream partials/#973 is
incomplete-signal only (continuation is the gap, row 243); MCP
`require_key_access_defined` is the template for row 244; `pricing.models`
overrides work (alias is the gap, row 245).

---

## Path to enterprise-grade — next 5 milestones

1. **Ride LiteLLM 1.109 where daari owns the levers** — compare watch (row
   242), mid-stream continuation (243), agent grant deny (244), pricing
   alias (245).
2. **Finish the Ollama 0.40.12 multimodal ride-along** — `lfm3-audio` (235),
   `lfm3-vl` (246); Linux operators via llama.cpp guide (241).
3. **Match Portkey v2.31.0 where daari already owns the data** — rows
   237–240.
4. **Pay down the observability honesty tail** — rows 225–226, 236, #1981,
   TTS/voices/skills P3s.
5. **Finish tenancy, then demand-gated protocols** — rows 62–67, hot-reload
   (6); row 8 (Realtime closer via llama.cpp) + parked row 7.

---

## Changelog

- **2026-10-28 pm (ride LiteLLM 1.109-dev; finish LFM3 text path)** — Marked
  rows 233–234 Shipped (#2000/#2001). LiteLLM **v1.109.0-dev.1** (prerelease)
  lands mid-stream fallback continuation, offline mode, agent_access_default_deny,
  pricing_provider, Admin Chat UI; GA floor stays 1.106.5. Filed rows 242–246.
  OpenAI Agents scheduled automations + Anthropic API 2026-10-21 remain watch.
  Portkey / llama.cpp / Ollama picture unchanged from the morning scan.

- **2026-10-28 (match Portkey v2.31.0, ride llama.cpp v0.8.0)** — Whole
  10-27 board merged in a day. Corrected stale Portkey version note; filed
  rows 237–241. llama.cpp v0.8.0 first semver; Ollama 0.40.12 Apple-only.

- **2026-10-27 + pm (finish what shipped; ride Ollama 0.40.12)** — Marked
  rows 217–224 Shipped; filed rows 227–236.

- **2026-10-26 + pm → 08-28** — Condensed: leases/at-rest/Terra through
  Apache 2.0 and this PRD's creation.
