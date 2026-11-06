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

## Where daari stands (verified in-tree, 2026-11-06)

**Loop velocity.** Overnight since the 11-05 PRD: rate-limit kind split by
scope (#2139), omitted-`temperature` ingress fix (#2140), batches webhook
rotation family (#2142), facade `/api/show` context/output limits (#2143) —
rows 294, 296–298 Shipped. The 11-04 Actions PRD PR #2127 is dead
(DIRTY + failed `test` check; its rows were adopted as 306–310 by #2138) —
stall flagged by issue #2141; drained via take-main this run.

**Outward.** **Ollama 0.40.15 GA** (2026-11-03 22:52 UTC — the 11-05 "rc1
only" read was stale): MiMo V2.6 9B code/agent model, **AutoTrust
(`autotrust-jev`) decision models** (9b/35b/27b-vl, vision on the big two,
Apple-silicon-only this release), Kimi Code CLI launch, Qwen3/3.5 YaRN
long-context, concurrent recurrent/vision GGUF. **LiteLLM v1.108.1**
(2026-11-05): LTS backports only, incl. a passthrough credential-selection
fix — floor row 306 (#2122, open) should land as 1.108.1. **Portkey
v2.33.1** (2026-11-06): fixes only (analytics Redis pub/sub retries, OTel
double-send on retried jobs, `NODE_EXTRA_CA_CERTS` in log uploads) — floor
v2.33.1. **Anthropic 11-05 (both beta):** org **IP allowlisting** (Console,
≤1,000 IPv4/IPv6 CIDRs) and Admin API **sign-out-everywhere** — the two
governance hooks this run converts. 11-03: text watermark on Mythos
5 / Opus 4.7 / Sonnet 4.6 (metric-only — Watch). **OpenAI:** gpt-6-cyber
(11-05, Daybreak restricted), gpt-image-2.6 sunburst/flare (11-04, SVG +
GIF + markup-guided edits), gpt-live-1 outbound SIP (11-02), Agents API
`auto_review` (10-30) — all Watch. vLLM still `v0.33.0rc3`-named-0.33.0;
Kong 3.9.4; MCP spec churn without a new revision. OpenRouter pages
unreachable this run (3 fetch timeouts) — recheck next run.

**Inward theme: leaked-credential blast radius.** Anthropic's two Nov-5
betas both contain stolen credentials at the org edge; daari has neither
twin — no IP binding on virtual keys/teams (auth only special-cases
loopback) and no revoke-by-subject offboarding path (per-`key_id` CLI
only). Both convert per-key/team and on-box, tighter than any org-wide
SaaS console dial.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 316 | Per-key/team client IP allowlist (CIDR) on virtual-key auth | 4 | 2 | Anthropic Console org IP allowlist (11-05 beta) | Per-key/team blast-radius control on-box, local tiers included | Filed [#2144](https://github.com/naveenreddyalka/daari/issues/2144) |
| 317 | Revoke every SSO-minted key for a subject (offboarding kill switch) | 4 | 2 | Anthropic Admin API sign-out-everywhere (11-05 beta) | One on-box call kills keys + team grants, no IdP webhook lag | Filed [#2145](https://github.com/naveenreddyalka/daari/issues/2145) |
| 318 | AutoTrust (`autotrust-jev`) local decision-model family | 3 | 2 | Ollama 0.40.15 / Portkey Clef decisions | Decisions stay on-box with budgets, guardrails, audit | Filed [#2146](https://github.com/naveenreddyalka/daari/issues/2146) |
| 319 | MiMo V2.6 L4 code/agent recipe | 3 | 1 | Ollama 0.40.15 | Agent loops on a 9B local tier, frontier only on escalation | Filed [#2147](https://github.com/naveenreddyalka/daari/issues/2147) |
| 320 | Integration fence for the 11-05/11-06 overnight wave | 2 | 2 | — (testability) | Hermetic proof: temp omit, rate kinds, show limits, rotation | Filed [#2148](https://github.com/naveenreddyalka/daari/issues/2148) |
| 311 | Stats/Prom for Anthropic message-threads create/continue/soft-ignore | 3 | 1 | Anthropic Claude Platform / Claude Code | Chart L6 thread pressure vs local fail-closed on-box | Filed [#2133](https://github.com/naveenreddyalka/daari/issues/2133) |
| 312 | Opt-in `user_agent` on OTel GenAI spans | 3 | 1 | Portkey v2.33.0 Complete Logs | IDE/agent attribution in operator-owned OTel | Filed [#2134](https://github.com/naveenreddyalka/daari/issues/2134) |
| 313 | Admin + web-ui surface for `virtual_model_latency_slo_ms` | 3 | 1 | OpenRouter performance analytics / LiteLLM Admin | Same-box console for the SLO dial selection already uses | Filed [#2135](https://github.com/naveenreddyalka/daari/issues/2135) |
| 314 | Opt-in omit requester `client_ip` from enterprise audit | 3 | 2 | LiteLLM 1.108.0 `disable_requester_ip_address_logging` | Privacy dial on operator-owned audit disk | Filed [#2136](https://github.com/naveenreddyalka/daari/issues/2136) |
| 315 | Integration fence for the 11-04 / 11-05 morning wave | 2 | 2 | — (testability) | Hermetic proof: threads, tags, SLO, OTel cost, TPD UI | Filed [#2137](https://github.com/naveenreddyalka/daari/issues/2137) |
| 306 | compare-litellm: promote GA floor to 1.108.0 LTS; note 1.109.0-rc.1 | 2 | 1 | LiteLLM LTS / release notes | Honest support window; no proxy pin | Filed [#2122](https://github.com/naveenreddyalka/daari/issues/2122) |
| 307 | Prom/stats counters for virtual-model latency SLO demotions | 3 | 1 | OpenRouter performance router analytics | SLO pressure from on-box EWMA | Filed [#2123](https://github.com/naveenreddyalka/daari/issues/2123) |
| 308 | Opt-in request tags on OTel GenAI spans | 3 | 1 | Portkey Complete Logs / LiteLLM tag dashboards | Workload tags next to local-tier cost attrs | Filed [#2124](https://github.com/naveenreddyalka/daari/issues/2124) |
| 309 | Config ownership + PATCH for `routing.virtual_model_latency_slo_ms` | 3 | 1 | LiteLLM / OpenRouter control planes | Hot-edit SLO ms without restart | Filed [#2125](https://github.com/naveenreddyalka/daari/issues/2125) |
| 310 | Integration fence for the 11-03 overnight / 11-04 morning wave | 2 | 2 | — (testability) | Hermetic proof: prior overnight dials | Filed [#2126](https://github.com/naveenreddyalka/daari/issues/2126) |
| 301 | Stats/Prom counters for `service_tier_not_allowed` deny + degrade | 3 | 1 | OpenAI Platform / LiteLLM spend | Governance cliffs on the same-box scrape | Filed [#2110](https://github.com/naveenreddyalka/daari/issues/2110) |
| 302 | Admin + web-ui surface for `allowed_service_tiers` | 3 | 1 | OpenAI Platform / LiteLLM Admin | Same-box console for the dial CLI already mints | Filed [#2111](https://github.com/naveenreddyalka/daari/issues/2111) |
| 303 | Route Codex PATs (`at-`) to the Codex backend on L6 | 3 | 2 | Portkey v2.32.0 OpenAI integration | Local tiers still win before Codex egress | Filed [#2112](https://github.com/naveenreddyalka/daari/issues/2112) |
| 304 | Prometheus counter for `X-Daari-Priority` admission overrides | 2 | 1 | LiteLLM / Portkey priority dashboards | Queue-steer pressure without a SaaS log plane | Filed [#2113](https://github.com/naveenreddyalka/daari/issues/2113) |
| 305 | Integration fence for the 11-03 afternoon governance/speech wave | 2 | 2 | — (testability) | Hermetic proof: allowlist 403/degrade + lfm3-audio | Filed [#2114](https://github.com/naveenreddyalka/daari/issues/2114) |
| 294, 296–298 | Rate-limit kind split; temperature omit; batches rotation; `/api/show` limits | 3–4 | 1–2 | LiteLLM / Ollama 0.40.14 | Byte-equivalence + signed push channels | Shipped (#2139–#2140, #2142–#2143) |
| 299 | Preserve assistant refusal parts in Responses input | 2 | 1 | Ollama 0.40.14 `/v1/responses` fix | Refusals survive tier hops | Shipped [#2105](https://github.com/naveenreddyalka/daari/issues/2105) |
| 300 | Integration fence for the 11-02/11-03 overnight wave | 2 | 2 | — (testability) | Hermetic proof: priority header, signed batch webhooks | Filed [#2106](https://github.com/naveenreddyalka/daari/issues/2106) |
| 291–293 | Message-threads; TPD web-ui; selection Grafana | 2–4 | 1–3 | Anthropic / LiteLLM / OpenRouter | TTFT parity + same-box console | Shipped (#2130–#2132) |
| 286–289 | OTel cost attrs; latency SLO; vLLM 0.33 notes; MCP oauth recipe | 2–3 | 1–2 | Portkey / OpenRouter / vLLM | Operator-owned traces + honest local tiers | Shipped (#2120–#2121, #2128–#2129) |
| 281–284 | LiteLLM LTS compare; offline PATCH; batch org webhook; request tags | 2–3 | 1–2 | LiteLLM / OpenRouter / Portkey | Honesty + air-gap + jobs + Signals on-box | Shipped (#2116–#2119) |
| 295 | Integration fence for the 11-02 afternoon wave | 2 | 2 | — (testability) | Hermetic proof: TPD + OpenRouter compare pin | Filed [#2097](https://github.com/naveenreddyalka/daari/issues/2097) |
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
| 279 | Prometheus counter for offline-mode refused egress | 2 | 1 | — (ops honesty) | Prove the air gap held from the scrape | Filed [#2072](https://github.com/naveenreddyalka/daari/issues/2072) |
| 285 | Doctor tip: offline_mode on + live frontier L6 creds | 2 | 1 | — (ops honesty) | Same-box warning before the 403 storm | Filed [#2079](https://github.com/naveenreddyalka/daari/issues/2079) |
| 274 | Grafana panels for `daari_virtual_model_failover_total` | 2 | 1 | Portkey analytics / hand-rolled Prom | Failover pressure on the same-box overview | Filed [#2059](https://github.com/naveenreddyalka/daari/issues/2059) |
| 277–278 | Service-tier allowlist; `lfm3-audio` speech-only recipe | 2–3 | 1–2 | OpenAI / Ollama | Deny 6× tiers; speech without omni weights | Shipped (#2108–#2109) |
| 271–273, 275–276 | TPD quotas; OpenRouter + LiteLLM compare; priority; signed batch webhooks | 2–3 | 1–2 | LiteLLM / OpenRouter | Day-grain dial, honest copy, queue steer | Shipped (#2091–#2092, #2099–#2101) |
| 62–67 | End-user inventory; guardrail profiles; web-ui pagination; nested usage | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger already meters; finish the console | Open (agent:working) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; OpenAI Live; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): Portkey v2.33 Anthropic `auto_caching` (daari
`frontier.prompt_cache` already marks system blocks — revisit only if
top-level `cache_control` shape diverges in client traffic); Portkey MCP
access policies (Prisma AIRS-only); Portkey OTel workspace name; Bedrock
metadata map; LiteLLM OpenAI Live `/v1/live/sessions` + Azure PTU split +
M365 Copilot provider + `gpt-live-1` outbound SIP (Realtime/WS family);
LiteLLM 1.109.0 stable cut; AutoTrust beyond Apple silicon (Linux/Windows
GA → revisit recipe caveat); `gpt-6-cyber` (Daybreak restricted access);
gpt-image-2.6 sunburst/flare catalog + markup-guided edits (images are
frontier passthrough today); Agents API `auto_review`; Anthropic text
watermark (Sonnet 4.6 non-default sampling caveat — metric-only);
minute-grain spend buckets; fleet
Redis EWMA; MCP SEP-3398 (~March 2027); OpenAI org external key management;
Anthropic Compliance API; Models API `between_tools` Sonnet-5.5-only;
`gpt-6-rosalind` catalog; Claude Code `groups` / `guardrail_trace`;
OpenRouter private-provider CRUD + S3/IAM; LiteLLM Admin Chat UI / Lens;
llama.cpp `/v1/realtime` + `POST /tts` + deferred tools; Portkey
claim-based JWT / WIF; OpenAI `/agents/automations`; Prisma AIRS Agent
Identity; Claude-on-GCP IAM (new dep — human); Anthropic hosted skills;
Claude Tag beta; Open Responses WS; Anthropic OTel export beta; Prom
exemplars + `gen_ai.agent.*`; LiteLLM ID-JAG; SCIM + multi-issuer SSO;
Kong Skills/A2A; OpenRouter Private Endpoints L6 recipe; certifi emSign;
Ollama d1 Linux/Windows GA; local message-thread analogue (prefix store on
L3–L5 — only after explicit agent-loop ask).

Verified fine this run — don't re-audit: auth has zero IP binding —
`key_lockout` / `invalid_key_throttle` only exempt loopback and
`client_ip_from_request` prefers the direct peer (row 316 rides it);
`keys revoke` is per-`key_id` only, SSO keys carry `client_id =
sso:<subject>` and `set_team_memberships` exists (row 317 wires them);
decisions already flatten `input_image` parts (#1886) and carry the d3/d1
catalog pattern (row 318); Flint L4 recipe is the one-command template
(row 319); all executors still None-guard `temperature` (#2140 was
ingress-only, as predicted); Ollama `launch` Kimi Code / Pi model list /
Claude Desktop naming = launcher surface, not daari; LiteLLM 1.108.1 is
backports-only; Portkey v2.33.1 is fixes-only; Ollama top stable
**0.40.15**; Portkey floor **v2.33.1**; LiteLLM compare floor promote
(row 306, #2122 open) should land as **1.108.1**.

---

## Path to enterprise-grade — next 5 milestones

1. **Contain the leaked key** — per-key/team IP allowlist (316);
   revoke-subject offboarding (317); audit IP omit (314) — the Anthropic
   Nov-5 governance pair, done per-tenant and on-box.
2. **Observe the TTFT / SLO dials** — thread counters (311); SLO demotion
   Prom (307) + PATCH (309) + console (313); selection Grafana shipped.
3. **Governance console tail** — service-tier Prom (301) + admin/web-ui
   (302); then rows 62–67.
4. **Local runtime at the Ollama 0.40.15 bar** — Responses refusals (299);
   AutoTrust decisions (318); MiMo recipe (319); fences (300, 305, 310,
   315, 320); UA spans (312) + request-tag spans (308).
5. **Air-gap + jobs + honesty** — Codex PAT L6 host (303); offline Prom
   (279) + doctor (285); admission Prom (304); LiteLLM 1.108.1 floor
   (306) + 1.109 watch; hot-reload (6).

---

## Changelog

- **2026-11-06 (leaked-key blast radius; Ollama 0.40.15 GA)** — Marked rows
  294, 296–298 Shipped (#2139–#2140, #2142–#2143). Outward: Ollama 0.40.15
  GA (MiMo V2.6, AutoTrust decisions, Kimi Code launch); LiteLLM 1.108.1
  backports; Portkey v2.33.1 fixes; Anthropic 11-05 IP-allowlist +
  sign-out-everywhere betas; OpenAI gpt-6-cyber / gpt-image-2.6 /
  gpt-live-1 SIP → Watch; OpenRouter unreachable. Filed rows 316–320: IP
  allowlist, revoke-subject, AutoTrust, MiMo recipe, 11-05/06 fence.
  Drained dead Actions PRD PR #2127 (stall flagged by issue #2141 — issue
  needs human close).

- **2026-11-05 (TTFT/SLO observe tail; Portkey 2.33 UA; LiteLLM IP omit; catch-up)** —
  Marked rows 281–284, 286–289, 291–293 Shipped. Adopted Nov-4 filings as
  rows 306–310 (LiteLLM 1.108 floor, SLO demotion Prom, OTel tags, SLO
  PATCH, fence). Outward: LiteLLM 1.108.0 LTS GA + 1.109.0-rc.1; Portkey
  v2.33.0; Ollama 0.40.15-rc1 only. Filed rows 311–315: thread stats/Prom,
  OTel user_agent, latency_slo console, audit client_ip omit, 11-04/11-05
  fence. Verified: threads/SLO/TPD/selection live without scrape/console
  tails; audit always stores client_ip; prompt_cache covers auto_caching
  watch.

- **2026-11-03 pm → 10-28** — Condensed: governance console / Codex PAT /
  admission Prom; Ollama 0.40.14 parity; message-threads / TPD / selection
  Grafana; trace cost / latency SLO / vLLM / MCP cc; LTS / air-gap / batch
  default / request tags; through Apache 2.0 and this PRD's creation.
