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

## Where daari stands (verified in-tree, 2026-10-29)

**Loop velocity.** The whole Portkey-parity board shipped overnight: per-rule
denial messages (#2009), per-server MCP timeouts (#2010), request-fact
signals + overrides (#2011), `lfm3-audio` speech recognition (#2008) — rows
235/237–239 Shipped within a day of filing, self-fenced in gateway-flow.
Open ride-along: LiteLLM-1.109 board (242–245), `lfm3-vl` (246), llama.cpp
guide (241), team Prom label (240), plus the P3 honesty tail.

**Outward.** **Ollama 0.40.13** (10-28) is the delta: LFM3 — including TTS in
`lfm3-audio` and `lfm3-omni` — now runs on **Linux and Windows**, killing the
Apple-only caveat daari's recipe copy still carries. **LiteLLM GA floor moves
to 1.106.6** (gzip scoping + off-loop compression backport — parity daari
shipped first in #1710); 1.108.0-rc.1 is a parity patch, watch. OpenAI 10-28
adds only a ChatGPT-subscriber API-credit perk (no gateway surface).
OpenRouter 10-29 adds private-provider CRUD (their SaaS BYO-GPU surface —
watch). Flat: Portkey v2.31.0, Anthropic (10-23), Kong, vLLM 0.32.0,
llama.cpp since v0.8.0, certifi still ships emSign.

**Inward theme: make yesterday's signals a real operator surface, and stop
telling Linux buyers LFM3 is Apple-only.** `SignalOverrideRule.match` is an
unvalidated free dict — typo keys and non-bucket values make rules silently
dead; `signal_overrides` is absent from the config-editor ownership allowlist
(config.yaml + restart only); the new `daari_signal_override_total{rule}`
series has no Grafana panel. LFM3 notes in `setup/models.py`, `--lfm3` help,
and `ollama.md` still say "Apple-first / coming soon"; the speech doctor
ignores `lfm3-omni`.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 247 | LFM3 notes ride Ollama 0.40.13 (Linux/Windows GA, omni TTS) | 3 | 1 | Ollama release notes | Linux fleets get the local tier the copy denies | Filed [#2012](https://github.com/naveenreddyalka/daari/issues/2012) |
| 248 | Validate `signal_overrides` match keys + bucket values | 3 | 1 | Portkey Signals UI validation | Dead rules fail loud in on-box config | Filed [#2013](https://github.com/naveenreddyalka/daari/issues/2013) |
| 249 | Config ownership + PATCH for `routing.signal_overrides` | 3 | 2 | LiteLLM / Portkey control planes | Tune routing live, no cloud control plane | Filed [#2014](https://github.com/naveenreddyalka/daari/issues/2014) |
| 250 | Grafana panel for `daari_signal_override_total` by rule | 2 | 1 | Portkey analytics tab | Rule visibility scraped next to the router | Filed [#2015](https://github.com/naveenreddyalka/daari/issues/2015) |
| 242 | compare-litellm: 1.109.0-dev.1 watch; GA floor 1.106.6 | 2 | 1 | LiteLLM release notes | Honest prerelease bar; on-box stance clear | Filed [#2002](https://github.com/naveenreddyalka/daari/issues/2002) |
| 243 | Mid-stream fallback continuation after upstream death | 4 | 3 | LiteLLM 1.109 mid-stream fallback | Continue on next local/L6 hop; no SaaS proxy | Filed [#2003](https://github.com/naveenreddyalka/daari/issues/2003) |
| 244 | Opt-in `agent_access_default_deny` for multi_agent keys | 4 | 2 | LiteLLM `agent_access_default_deny` | Same trust floor as MCP grants, on-box | Filed [#2004](https://github.com/naveenreddyalka/daari/issues/2004) |
| 245 | Optional `pricing_provider` / alias_of per model rates | 3 | 2 | LiteLLM `model_info.pricing_provider` | FinOps truth for aliases without cloud cost-map | Filed [#2005](https://github.com/naveenreddyalka/daari/issues/2005) |
| 246 | Optional `lfm3-vl` multimodal setup recipe + doctor tip | 3 | 2 | Ollama `ollama run lfm3-vl` | Vision agent turns stay local | Filed [#2006](https://github.com/naveenreddyalka/daari/issues/2006) |
| 237 | Per-rule custom guardrail denial messages | 3 | 1 | Portkey v2.31.0 custom errors | Operator-owned denial copy, on-box | Shipped (#2009) |
| 238 | Per-server MCP egress request timeout | 3 | 1 | Portkey per-integration timeouts | Tune each local hop; honest breakers | Shipped (#2010) |
| 239 | Request-fact signals in `daari_meta` + opt-in overrides | 4 | 3 | Portkey Signals beta | Facts already free on-box | Shipped (#2011) |
| 240 | Opt-in `team` label on requests/errors Prom series | 3 | 2 | Portkey `PROMETHEUS_EXTRA_LABELS` | Per-team traffic scraped on-box | Filed [#1997](https://github.com/naveenreddyalka/daari/issues/1997) |
| 241 | llama.cpp v0.8.0 local-tier guide + landscape refresh | 2 | 1 | llama.cpp release notes | Linux path to LFM3/d1 today | Filed [#1998](https://github.com/naveenreddyalka/daari/issues/1998) |
| 233 | Optional LFM3 L3 setup recipe (256K local agent tier) | 3 | 2 | Ollama `ollama run lfm3` | One setup prompt, on-box | Shipped (#2000) |
| 234 | Doctor tip when Ollama serves d1/lfm3 but unused | 3 | 1 | — (ops honesty) | Point at local win before L6 | Shipped (#2001) |
| 235 | Recognize `lfm3-audio` as local ASR/TTS beside Phonon | 3 | 2 | Ollama speech / Phonon | 18-language local speech | Shipped (#2008) |
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
outbound fetches — file after pricing alias lands); per-key/team-scoped
`signal_overrides` (after rows 248–249 prove out); `lfm3-omni` recipe / omni
routing matrix (after `lfm3-vl` row 246 merges); LiteLLM 1.108.0-rc.1 (parity
patch) + Admin Chat UI / Lens (non-goal); llama.cpp `/v1/realtime` + `POST
/tts` (pairs with row-8 Realtime/WS); llama.cpp deferred tools +
`tool_reference`; Portkey claim-based JWT; OpenRouter private-provider CRUD
(10-29, SaaS BYO-GPU) + S3/IAM destinations; OpenAI `/agents/automations`
passthrough; Prisma AIRS Agent Identity; Claude-on-GCP IAM egress (new dep —
human sign-off); Anthropic hosted `/v1/skills` proxy; Claude Tag beta
(non-goal); Open Responses WS; Anthropic OTel export beta; Prometheus
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG / OAuth-delegate; Portkey WIF;
SCIM + multi-issuer SSO; Kong Skills/A2A; OpenRouter Private Endpoints L6
recipe; certifi emSign drop (still ships 2026.10.23); MCP SEP-3415 /
SEP-3392 / Skills-spec-to-beta links when merged; Ollama d1 Linux/Windows GA
(0.40.13 names LFM3 only).

Verified fine this run — don't re-audit: gzip already off-loop
(`asyncio.to_thread`, 16 KiB floor, SSE/pre-encoded exempt — LiteLLM 1.106.6
is parity daari shipped in #1710); Portkey Signals **classifier mode**
substantially covered (local `routing.decision_classifier` refines
`profile.category` *before* `_apply_signal_overrides` reads it — kill that
watch row); Ollama facade serves `/api/version`; tts/asr docs platform-honest
(gap is recipe/CLI/ollama.md copy only, row 247); the 10-28 wave self-fenced
in `tests/integration/test_gateway_flow.py`; stream partials/#973 is
incomplete-signal only (continuation is the gap, row 243); MCP
`require_key_access_defined` is the template for row 244; `pricing.models`
overrides work (alias is the gap, row 245).

---

## Path to enterprise-grade — next 5 milestones

1. **Ride LiteLLM 1.109 where daari owns the levers** — compare watch (row
   242), mid-stream continuation (243), agent grant deny (244), pricing
   alias (245), then the `LITELLM_OFFLINE_MODE` analog watch.
2. **Make signals an operator surface** — validation (248), config-editor
   ownership (249), Grafana panel (250); then per-key/team binding (watch).
3. **Finish the Ollama 0.40.13 multimodal ride-along** — platform notes +
   omni TTS (247), `lfm3-vl` (246), llama.cpp guide (241); omni recipe after.
4. **Pay down the observability honesty tail** — row 240, rows 225–226, 236,
   #1981, TTS/voices/skills P3s.
5. **Finish tenancy, then demand-gated protocols** — rows 62–67, hot-reload
   (6); row 8 (Realtime closer via llama.cpp + Portkey GPT Live) + parked
   row 7.

---

## Changelog

- **2026-10-29 (signals become an operator surface; LFM3 goes Linux)** —
  Marked rows 235/237–239 Shipped (#2008–#2011, merged within a day,
  self-fenced). Ollama **0.40.13** ships LFM3 incl. `lfm3-audio`/`lfm3-omni`
  TTS on Linux/Windows — filed row 247 (stale Apple-only copy + omni doctor).
  Filed rows 248–250 hardening yesterday's signals ship (match validation,
  config ownership, Grafana panel). LiteLLM GA floor → **1.106.6** (gzip
  backport = daari #1710 parity, verified off-loop). Killed the Signals
  classifier-mode watch row (local classifier already feeds overrides).

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
