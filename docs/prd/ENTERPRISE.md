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

## Where daari stands (verified in-tree, 2026-10-20)

**Loop velocity.** The whole 10-19 board drained in under 24 hours: morning
rows 150–157 and evening rows 158–160 all merged (speed-keyed L0/L1 caches,
Helm/auth/breaker/doctor for the decisions upstream, spend export filters,
`schema_ok` scrape + banner, events console filters). Evening rows 161–162
stay open. Admin-plane rows 6/62–63/65–67 unchanged.

**Outward.** Flat on GA: LiteLLM 1.106.0 (1.104.4 is a backport patch;
1.107.0-rc.2 carries an MCP ID-JAG/OAuth-delegate identity stack and a
count_tokens stack — watch at GA), Portkey v2.29.0, Kong 2.2.0 /
Gateway 3.16.0.1, OpenRouter (Oct 9), vLLM 0.32.0, Ollama 0.40.7-rc0.
Anthropic's 10-15 notes now list `capabilities.thinking.types.between_tools`
on the Models API (watch row below).

**Inward theme: finish the knobs the wave shipped.** The systemone Bearer
token exists but Helm cannot mount it (frontier has `apiKeySecret`; systemone
does not). Spend `--model`/`--usage-speed` filters are CLI-only — no HTTP
export, no console controls, chargeback doc silent. The systemone breaker
counts trips but exposes no current state on stats/doctor/console. Neither
`daari_schema_ok` nor `daari_systemone_breaker_total` reaches the shipped
Grafana dashboard or PrometheusRule pack. The events plane filters key/kind
but has no `since`/`until` anywhere.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 163 | Helm `systemone.apiKeySecret` mounts `DAARI_SYSTEMONE__API_KEY` (frontier pattern) | 4 | 1 | LiteLLM Helm provider creds | Authenticated on-prem judge boxes deploy from the chart | Filed [#1820](https://github.com/naveenreddyalka/daari/issues/1820) |
| 164 | HTTP spend export with `model`/`usage_speed` filters + console controls + chargeback doc | 4 | 3 | LiteLLM /spend/logs, Portkey analytics | Filtered chargeback rows without shell access to the pod | Filed [#1821](https://github.com/naveenreddyalka/daari/issues/1821) |
| 165 | systemone breaker state on stats/doctor/metrics/console (counter-only today) | 4 | 3 | Kong/Envoy upstream state | A fenced judge hop changes routing — the box must say so | Filed [#1822](https://github.com/naveenreddyalka/daari/issues/1822) |
| 166 | Grafana + PrometheusRule coverage for `daari_schema_ok` and the systemone breaker series | 3 | 1 | LiteLLM packaged dashboards | Schema lag and judge fencing page from the on-box scrape | Filed [#1823](https://github.com/naveenreddyalka/daari/issues/1823) |
| 167 | Events `since`/`until` across store/API/console/CLI + CLI `--key` parity | 3 | 2 | Kong analytics time slices | Incident triage on the local request log, bounded to the window | Filed [#1824](https://github.com/naveenreddyalka/daari/issues/1824) |
| 161 | Budget webhooks: ISO `reset_at` + `model_max_budget` threshold crossings | 4 | 2 | Portkey / LiteLLM per-model budgets | Same reset clock as the 402, including model caps | Open |
| 162 | Gateway integration flow pins explicit `systemone.base_url` (unit MockTransport only today) | 2 | 1 | — (testability) | The named decisions host is what the suite proves | Open |
| 150–160 | 10-19 waves: speed-keyed L0/L1 caches; systemone base_url/auth/breaker/Helm/doctor/executor labels; spend `--model`/`--usage-speed` + Grafana cloud/fast panels; `schema_ok` scrape + banner; events console filters | 2–4 | 1–3 | LiteLLM / vLLM / Portkey | Cache truth, governed judge upstream, FinOps slices on-box | Shipped |
| 136–149 | 10-18 waves: `resultType` everywhere; fast-mode stream degrade/headers/billing; `:cloud` fences + catalog markers; replay/ledger honesty; configurable systemone upstream; 1.106 GA floor | 2–5 | 1–3 | Claude Code / Anthropic / LiteLLM / vLLM | Protocol, egress, and billing truth on-box | Shipped |
| 131 | Ollama `:cloud` counts as remote egress for `no_frontier` / PII scrub / region fences | 5 | 2 | Portkey egress fences | "Local-only means local-only" is the core promise | Shipped |
| 117–130 | 10-16/10-17 waves: modality 410; Opus fast billing; scoped reads; lockout unlock; Helm consistent backup; client recipes; catalog/doctor/ready honesty | 2–5 | 1–3 | — / Ollama / LiteLLM | Lifecycle, tenancy, DR, onboarding on-box | Shipped |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 107–116 | 10-15 waves: retired-410 facades; team-scoped reads; consistent backup; TLS doctor; webhook secret rotation; traceresponse; events HTTP; key lockout; Grafana errors-by-status; chatgpt-desktop | 3–5 | 1–4 | — / Kong / LiteLLM 1.107-dev | Lifecycle + tenancy + DR + trace round-trip on-box | Shipped |
| 90/91/78 | Member budget webhooks; DEC/SYS bench docs; LiteLLM 1.106 compare note | 2–3 | 1–3 | LiteLLM 1.105/1.106 | Runaway-agent alerts + benchmarking honesty | Shipped |
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
| 8 | Full DCR; A2A (Kong 3.16.0.1 speaks v1.0); Realtime/WS (incl. GPT-Live Decisions); stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): speed in L0 fingerprint + L1 context key;
configurable systemone upstream with Bearer auth, circuit breaker, classifier
pool, Helm baseUrl knob + NetworkPolicy, doctor catalog probe + resolved-root
naming, `daari_meta` executor label, upstream request ids; spend export
`--model`/`--usage-speed` + Grafana cloud/fast panels; `daari_schema_ok`
scrape + console banner; events console key/kind filters + payload text;
fence-aware session pins; `:cloud` catalog markers; `resultType` on
`tools/call`, OpenAPI proxy, and `tasks/get`.

Watch rows (do not file yet): Anthropic `capabilities.thinking.types.
between_tools` on catalog cards + local-tier graceful degrade (egress already
forwards the dict verbatim — fold into the next catalog sweep); cache
invalidate by `speed` selector (model-prefix invalidate still clears both
modes — file on operator ask); LiteLLM 1.107 GA watchables (MCP ID-JAG
identity-assertion grants + OAuth Delegate/gateway-owned DCR bridge,
`agent_access_default_deny`, count endpoints erroring in source-API shape);
systemone multi-upstream / opt-in Ollama fallback when the explicit base is
down (fleet demand); gzip compression Prom metrics (operator ask);
`CONFIGURE_CLIENTS` first-wave tuple lags the registry (trivial, fold into
next recipe); cursor-agent CLI configure; `migrate --downgrade`
(demand-triggered); Responses background completion webhooks + wider
`include` allowlist; per-user request-count RPD (USD caps only); SCIM +
multi-issuer/audience SSO; Prometheus exemplars + `gen_ai.agent.*` spans +
PG request-log concurrency/soak tests; Portkey v2.29 JWT claims→metadata
conditional routing (buyer ask); Kong `ai-proxy-advanced` byte-preserving
forwards for provider prompt caches (re-check on cache-hit complaints);
Anthropic Compliance API user-preferences export + OpenAI GPT-Live
prompt-to-voice (non-goals).

Verified fine this run — don't re-audit: `systemone.api_key` resolves
`secret://` refs (generic settings walk), is absent from GET/PATCH
`/v1/daari/config`, and doctor probes send the Bearer without echoing it;
Opus 5.5 fast-mode GA vs Opus 5/4.8 preview beta gating correct in
`resolve_anthropic_speed` (daari never injects the beta header itself);
model-prefix cache invalidate still clears both speed variants (context key
appends `speed:` after the model segment); systemone breaker trips do emit
`daari_systemone_breaker_total` + a gateway event + 503 Retry-After (gap is
state visibility, row 165); `daari events list` CLI verb exists (gap is
filters, row 167); `thinking` dicts forward verbatim to Anthropic L6.

---

## Path to enterprise-grade — next 5 milestones

1. **Deploy the judge-box auth from the chart** — `systemone.apiKeySecret`
   mounting `DAARI_SYSTEMONE__API_KEY` exactly like frontier (row 163).
2. **Chargeback over HTTP, not just shell** — spend export with model and
   usage-speed filters on the admin API, console, and docs (row 164).
3. **Say when the judge hop is fenced** — systemone breaker state on
   stats, doctor, metrics, and the console (row 165), and page on it plus
   schema lag from the packaged dashboard/alert rules (row 166).
4. **Bound incident triage in time** — `since`/`until` on the events
   store, API, console, and CLI (row 167).
5. **Model-cap alerts on the same clock as the 402** — ISO `reset_at` +
   `model_max_budget` crossings on budget webhooks (row 161), plus the
   gateway-flow pin for the explicit systemone base (row 162).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-20 (finish the knobs the wave shipped)** — Marked rows 150–160
  Shipped (the whole 10-19 board merged in <24h). Filed rows 163–167: Helm
  `systemone.apiKeySecret`, HTTP spend export with model/usage-speed
  filters, systemone breaker state surfaces, Grafana + PrometheusRule
  coverage for `schema_ok` and the breaker series, and events
  `since`/`until` windows. Outward flat: LiteLLM 1.106.0 GA (1.104.4
  backport patch; 1.107.0-rc.2 MCP ID-JAG/OAuth-delegate + count_tokens
  stacks on watch), Portkey v2.29.0, Kong 2.2.0/3.16.0.1, OpenRouter,
  vLLM 0.32.0, Ollama 0.40.7-rc0. New watch: Anthropic
  `capabilities.thinking.types.between_tools` (10-15 Models API field).

- **2026-10-19 evening (L1 speed alias, alert clock, console honesty)** —
  Filed rows 158–162: L1 `speed` context key, `schema_ok` gauge and console
  banner, events key/kind/payload UI, budget-webhook ISO `reset_at` plus
  model-cap crossings, and a gateway-flow pin for explicit
  `systemone.base_url`. Outward flat.

- **2026-10-19 (depth behind the configurable decisions upstream +
  fast-mode cache truth)** — Marked rows 136–149 Shipped. Added rows
  150–152 (loop's systemone refill) and filed rows 153–157: L0 `speed`
  cache fingerprint, Helm/NetworkPolicy knobs for `systemone.base_url`,
  upstream `api_key` Bearer, systemone circuit breaker + pooled classifier
  hop, and spend export/Grafana slices for `:cloud` and fast-mode.
  Noted Kong Gateway 3.16.0.1 (`ai-a2a-proxy` A2A v1.0, byte-preserving
  `ai-proxy-advanced` forwards).

- **2026-10-18 (three scans: 1.106 GA floor; replay/count/ledger honesty;
  stream-path fast mode + egress truth + vLLM 0.32)** — Rows 136–149 across
  the day: `tools/call`/proxy `resultType`, fast-mode rate-limit headers and
  stream degrade, adaptive thinking key strip, trailing empty user turns,
  image/document `count_tokens`, web-search call fees, upstream request ids,
  `speed`-ignored warning, fence-aware session pins, `:cloud` catalog
  markers, configurable systemone upstream. vLLM 0.32.0 serves
  `POST /v1/systemone` by default.

- **2026-10-17 → 08-28** — Condensed: three 10-17 scans (egress truth,
  stream billing, ops surfaces; protocol cache hints + Ollama cloud/quant
  honesty; client recipes + upgrade skew); edge-depth lifecycle doors +
  tenancy totals + fast mode + deploy defaults; post-wave lifecycle/
  tenancy/DR/TLS depth; overnight-wave parity; day-2 operations +
  observability packaging; concurrency + decision-guardrail depth;
  control-plane honesty + MCP server rpm; export honesty + doctor ACL;
  team DR + console lifecycle; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
