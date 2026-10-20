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

## Where daari stands (verified in-tree, 2026-10-20 evening)

**Loop velocity.** Morning rows 163–167 are filed and still open (Helm
systemone secret, HTTP spend filters, breaker state, Grafana/alert coverage,
events time windows). Evening scan does not wait on them — it closes the
honesty gaps the speed-keyed cache wave left on the watch list.

**Outward.** LiteLLM **1.107.0-rc.2** published today (still prerelease;
stable floor remains **1.106.0 GA**). Notable RC deltas vs the morning note:
OAuth consent scoped to `x-mcp-servers` + `mcp_require_explicit_server_scope`,
verified stateless MCP capabilities, `agent_access_default_deny`, ID-JAG /
OAuth-delegate depth, cosign-signed images. Portkey Enterprise changelog
surface still tops out at v2.20.0 in public docs (prior v2.29 label was a
stale shorthand — keep watching). Kong AI Gateway 2.2 / Gateway 3.16.0.1,
OpenRouter (Oct 9 end-user length bumps), vLLM 0.32.0, Ollama 0.40.7-rc0
(PPLX Decider v1.2 on MLX) unchanged at GA.

**Inward theme: speed-keyed ops + catalog/configure honesty.** L0/L1 now
key by Anthropic `speed`, but invalidate still clears both modes. `daari
configure`'s first-wave tuple lags the full client registry. Models API
cards omit `thinking.types.between_tools` while egress already forwards the
dict. compare-litellm's RC watch is still pinned to rc.1. Gzip middleware
ships with no Prom series.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 168 | Cache invalidate by Anthropic `speed` (CLI + HTTP + L0/L1) | 3 | 2 | LiteLLM / vLLM request-shape bust | Purge fast rows without wiping standard on-box | Filed [#1826](https://github.com/naveenreddyalka/daari/issues/1826) |
| 169 | `daari configure` first-wave lists every shipped client recipe | 3 | 1 | — (onboarding) | One local CLI matches the registry operators actually use | Filed [#1827](https://github.com/naveenreddyalka/daari/issues/1827) |
| 170 | Catalog `thinking.types.between_tools` + local-tier degrade | 3 | 2 | Anthropic Models API / Portkey | Honest cards; safe local refuse without a cloud hop | Filed [#1828](https://github.com/naveenreddyalka/daari/issues/1828) |
| 171 | compare-litellm: cite 1.107.0-rc.2 watchables; keep 1.106 GA floor | 2 | 1 | LiteLLM release notes | Positioning stays honest while RC churns | Filed [#1829](https://github.com/naveenreddyalka/daari/issues/1829) |
| 172 | Prometheus counters for gzip JSON compression | 2 | 1 | Kong/Envoy compression metrics | Same-box scrape shows Accept-Encoding payoff | Filed [#1830](https://github.com/naveenreddyalka/daari/issues/1830) |
| 163 | Helm `systemone.apiKeySecret` mounts `DAARI_SYSTEMONE__API_KEY` | 4 | 1 | LiteLLM Helm provider creds | Authenticated on-prem judge boxes deploy from the chart | Open |
| 164 | HTTP spend export with `model`/`usage_speed` + console + chargeback doc | 4 | 3 | LiteLLM /spend/logs, Portkey analytics | Filtered chargeback without shell access to the pod | Open |
| 165 | systemone breaker state on stats/doctor/metrics/console | 4 | 3 | Kong/Envoy upstream state | A fenced judge hop must be visible on the box | Open |
| 166 | Grafana + PrometheusRule for `schema_ok` and systemone breaker | 3 | 1 | LiteLLM packaged dashboards | Schema lag and judge fencing page from on-box scrape | Open |
| 167 | Events `since`/`until` across store/API/console/CLI | 3 | 2 | Kong analytics time slices | Incident triage bounded to the window | Open |
| 161 | Budget webhooks: ISO `reset_at` + `model_max_budget` crossings | 4 | 2 | Portkey / LiteLLM per-model budgets | Same reset clock as the 402, including model caps | Open |
| 162 | Gateway integration flow pins explicit `systemone.base_url` | 2 | 1 | — (testability) | The named decisions host is what the suite proves | Open |
| 150–160 | 10-19 waves: speed-keyed caches; systemone auth/breaker/Helm/doctor; spend slices; schema_ok; events filters | 2–4 | 1–3 | LiteLLM / vLLM / Portkey | Cache truth, governed judge, FinOps on-box | Shipped |
| 136–149 | 10-18 waves: `resultType`; fast-mode stream/billing; `:cloud` fences; systemone upstream; 1.106 floor | 2–5 | 1–3 | Claude Code / Anthropic / LiteLLM / vLLM | Protocol, egress, billing truth on-box | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): speed in L0 fingerprint + L1 context key;
configurable systemone upstream with Bearer auth, circuit breaker, classifier
pool, Helm baseUrl + NetworkPolicy, doctor probes, `daari_meta` executor
label, upstream request ids; spend CLI `--model`/`--usage-speed` + Grafana
cloud/fast panels; `daari_schema_ok` scrape + console banner; events console
key/kind filters; fence-aware session pins; `:cloud` catalog markers;
`resultType` on `tools/call`, OpenAPI proxy, and `tasks/get`.

Watch rows (do not file yet): LiteLLM 1.107 GA cut (`agent_access_default_deny`
as comparison bar, ID-JAG/OAuth-delegate DCR bridge, cosign image signing,
count endpoints source-API errors); systemone multi-upstream / opt-in Ollama
fallback when the explicit base is down; cursor-agent CLI configure;
`migrate --downgrade`; Responses background completion webhooks + wider
`include` allowlist; per-user request-count RPD (USD caps only); SCIM +
multi-issuer/audience SSO; Prometheus exemplars + `gen_ai.agent.*` spans +
PG request-log concurrency/soak; Portkey JWT claims→metadata conditional
routing (buyer ask); Kong `ai-proxy-advanced` byte-preserving provider prompt
caches (re-check on cache-hit complaints); Anthropic Compliance API
user-preferences export + OpenAI GPT-Live prompt-to-voice (non-goals).

Verified fine this run — don't re-audit: model-prefix cache invalidate still
clears both speed variants (gap is the speed selector, row 168);
`CONFIGURE_CLIENTS` still the three-tuple while registry has nine recipes
(row 169); `anthropic_capabilities` emits `disabled` (+ Haiku `adaptive`)
only (row 170); compare-litellm RC section still says rc.1 (row 171);
`GzipJsonMiddleware` compresses with zero Prom series (row 172); thinking
dicts still forward verbatim to Anthropic L6; systemone `api_key` still
resolves `secret://` and stays off GET/PATCH config.

---

## Path to enterprise-grade — next 5 milestones

1. **Purge one speed mode without wiping the other** — cache invalidate by
   `speed` on L0/L1, CLI, and HTTP (row 168).
2. **Configure lists every client the registry ships** — first-wave + verify
   curls match Cursor/Claude/ChatGPT Desktop and the rest (row 169).
3. **Honest thinking catalog** — `between_tools` on cards + safe local-tier
   degrade (row 170), while L6 keeps forwarding verbatim.
4. **Finish the morning ops plane** — Helm systemone secret, HTTP spend
   filters, breaker state + Grafana/alerts, events time windows
   (rows 163–167), plus budget-webhook ISO `reset_at` (row 161).
5. **Keep the LiteLLM floor honest** — document 1.107.0-rc.2 watchables
   without promoting them past 1.106 GA (row 171), and expose gzip payoff
   on the scrape (row 172).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-20 evening (speed-keyed ops + catalog/configure honesty)** —
  Filed rows 168–172: cache invalidate by `speed`, `daari configure`
  first-wave vs full registry, `thinking.types.between_tools` catalog +
  local degrade, compare-litellm 1.107.0-rc.2 watch note (1.106 GA floor
  unchanged), gzip Prometheus counters. Outward: LiteLLM 1.107.0-rc.2
  today; Portkey public Enterprise changelog still v2.20.0; Kong 2.2 /
  3.16.0.1, OpenRouter, vLLM 0.32.0, Ollama 0.40.7-rc0 flat at GA.
  Morning rows 163–167 remain open.

- **2026-10-20 (finish the knobs the wave shipped)** — Marked rows 150–160
  Shipped. Filed rows 163–167: Helm `systemone.apiKeySecret`, HTTP spend
  export with model/usage-speed filters, systemone breaker state surfaces,
  Grafana + PrometheusRule coverage for `schema_ok` and the breaker series,
  and events `since`/`until` windows. Outward flat on 1.106 GA /
  1.107.0-rc.2 watch.

- **2026-10-19 evening (L1 speed alias, alert clock, console honesty)** —
  Filed rows 158–162: L1 `speed` context key, `schema_ok` gauge and console
  banner, events key/kind/payload UI, budget-webhook ISO `reset_at` plus
  model-cap crossings, and a gateway-flow pin for explicit
  `systemone.base_url`. Outward flat.

- **2026-10-19 (depth behind the configurable decisions upstream +
  fast-mode cache truth)** — Marked rows 136–149 Shipped. Added rows
  150–152 and filed rows 153–157 (L0 speed fingerprint, Helm/NetworkPolicy
  systemone baseUrl, upstream Bearer, circuit breaker + classifier pool,
  spend/Grafana cloud/fast slices). Noted Kong Gateway 3.16.0.1.

- **2026-10-18 → 08-28** — Condensed: three 10-18 scans (1.106 GA floor;
  replay/count/ledger honesty; stream-path fast mode + egress truth + vLLM
  0.32); 10-17 egress/stream/ops; protocol cache hints + Ollama cloud/quant
  honesty; client recipes + upgrade skew; edge-depth lifecycle + tenancy +
  fast mode + deploy defaults; overnight-wave parity; day-2 operations +
  observability packaging; concurrency + decision-guardrail depth;
  control-plane honesty + MCP server rpm; export honesty + doctor ACL;
  team DR + console lifecycle; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
