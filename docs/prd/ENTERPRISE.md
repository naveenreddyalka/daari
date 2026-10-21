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

## Where daari stands (verified in-tree, 2026-10-21 pm)

**Loop velocity.** Morning rows 173–177 are still open (breaker truth, OpenAI
TTL cache billing, user-profile forward, invalidate tenancy, facade `show`).
P3 leftovers 171–172 remain. Same-day evening scan found a supply-chain
crisis and an Anthropic API-version footgun that outrank the leftovers.

**Outward.** **LiteLLM v1.107.0 is compromised** (2026-10-21): PyPI wheels and
the official Docker image carried an infostealer + RAT; PyPI quarantined the
version and the image was pulled. Safe GA floor stays **1.106.2**. Do not
install or recommend 1.107.0. **Anthropic API version `2026-10-21`** shipped
today: removes `temperature`/`top_p`/`top_k` (HTTP 400); new SDKs/`ant` CLI
default to that version and are Apache 2.0. Ollama **0.40.8-rc0** adds
Recursive Flint (40B-MoE coder, Mac-first). Portkey/Kong/OpenRouter/vLLM/MCP
flat vs morning scan.

**Inward theme: stop poisoning the Anthropic hop, and own the supply-chain
story.** `AnthropicRequest.temperature` defaults to `0.7`, so every Messages
request that omits sampling still injects temperature into `InternalRequest`
and the L6 Anthropic payload — fatal under `anthropic-version: 2026-10-21`.
`compare-litellm.md` still treats 1.107 as a benign RC watch and pins the
floor at 1.106.0. Spend export is HTTP/CLI-only (no console). Local
`thinking.between_tools` degrade is `dropped_params`-only (no soft_warning /
Prom). Flint is not yet a setup/models recipe.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 178 | compare-litellm: LiteLLM 1.107.0 compromise advisory; GA floor 1.106.2 | 5 | 1 | Aikido / PyPI quarantine notes | Local-first pip install never touched the poisoned proxy | Filed [#1848](https://github.com/naveenreddyalka/daari/issues/1848) |
| 179 | Anthropic API `2026-10-21`: no default temperature; strip sampling on that version | 5 | 2 | Anthropic SDK 2.0 | New Claude Code/SDK clients must not 400 on the L6 hop | Filed [#1849](https://github.com/naveenreddyalka/daari/issues/1849) |
| 180 | Web console: download via `GET /v1/daari/spend/export` | 3 | 2 | LiteLLM admin UI | FinOps CSV/JSONL without leaving the box | Filed [#1850](https://github.com/naveenreddyalka/daari/issues/1850) |
| 181 | soft_warning + Prom when local strips `thinking.between_tools` | 3 | 1 | LiteLLM compact telemetry | Same-box scrape shows catalog degrade, not silent drops | Filed [#1851](https://github.com/naveenreddyalka/daari/issues/1851) |
| 182 | Setup/models: optional Flint L4 coding recipe (Ollama ≥0.40.8) | 2 | 1 | Ollama `run flint` | Local coding MoE on the cheapest capable tier | Filed [#1852](https://github.com/naveenreddyalka/daari/issues/1852) |
| 173 | systemone breaker truth: doctor via daemon stats, `/ready` component, admin reset | 5 | 2 | Kong/Envoy upstream state | Fenced judge hop visible and clearable on the box | Open |
| 174 | Bill OpenAI prompt-cache writes by TTL (30m 1.25× / 12h 2.5×) | 4 | 2 | OpenAI invoice / LiteLLM | Ledger/budgets match the provider invoice | Open |
| 175 | Forward `anthropic-user-profile-id` + map end users | 4 | 2 | — (Anthropic 10-20) | Enforcement blast-radius shrinks to one tenant | Open |
| 176 | Team-scope cache invalidate; audit offline CLI | 4 | 2 | — (tenancy depth) | Per-tenant cache control with local audit | Open |
| 177 | Facade `/api/show` parity: Ollama 0.40.7 fields | 3 | 1 | Ollama | Ollama-native clients notice nothing | Open |
| 171 | compare-litellm RC.2 watchables (superseded by row 178) | 2 | 1 | LiteLLM release notes | Superseded — do not implement as written | Superseded |
| 172 | Prometheus counters for gzip JSON compression | 2 | 1 | Kong/Envoy compression metrics | Accept-Encoding payoff on-box | Open |
| 161–170 | 10-19 eve + 10-20 waves (systemone secret, webhooks, spend export HTTP, breaker surfaces, Grafana, events windows, speed invalidate, configure, `between_tools`) | 2–4 | 1–3 | LiteLLM / Portkey / Kong | FinOps, judge ops, catalog honesty | Shipped |
| 150–160 | 10-19 waves: speed-keyed caches; systemone auth/breaker/Helm; spend slices; `schema_ok`; events filters | 2–4 | 1–3 | LiteLLM / vLLM / Portkey | Cache truth + governed judge + FinOps | Shipped |
| 136–149 | 10-18 waves: `resultType`; fast-mode; `:cloud` fences; replay/ledger; systemone upstream; 1.106 floor | 2–5 | 1–3 | Claude Code / LiteLLM / vLLM | Protocol, egress, billing truth | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Shipped this week (do not re-file): Helm `systemone.apiKeySecret`; budget
webhooks ISO `reset_at` + `model_max_budget`; HTTP spend export (analyst +
team scope + audit); breaker on stats/doctor/console; Grafana/`schema_ok` +
breaker alerts; events `since`/`until`; speed-keyed invalidate; configure
first-wave; catalog `between_tools` + local degrade via `dropped_params`.

Watch rows (do not file yet): Anthropic org restrict/ban webhook ingest →
auto-block mapped end user (after row 175); shared multi-replica breaker
store; `doctor-health.md` tip fold into 173; LiteLLM post-quarantine clean
1.107 rebuild watchables (ID-JAG/OAuth-delegate, `agent_access_default_deny`)
only after a verified non-compromised GA; Ollama Flint GPU beyond Mac +
`ollama launch` parity; OpenAI Agents ultrafast `service_tier` depth;
systemone multi-upstream; cursor-agent CLI configure; `migrate --downgrade`;
Responses background completion webhooks; per-user RPD; SCIM + multi-issuer
SSO; Prometheus exemplars + `gen_ai.agent.*`; Kong Skills/passthrough
demand; OpenAI-on-Google-Cloud + Anthropic Compliance user-preferences
(non-goals).

Verified fine this run — don't re-audit: spend export enforces analyst +
team scope + audit; `model_max_budget` webhook dedupe; events console
`since`/`until`; `CONFIGURE_CLIENTS` pin; HTTP invalidate admin+audit (gap
is team scope, row 176); breaker self-recovers (gap is doctor/ready/reset,
row 173); `prompt_cache_options` forwards (gap is billing, row 174);
Sonnet 5.5 `cached_input_per_1m` already 0.10 (0.05×).

---

## Path to enterprise-grade — next 5 milestones

1. **Own the supply-chain narrative** — compare-litellm must say 1.107.0 is
   unsafe and pin the floor at 1.106.2 (row 178).
2. **Stop 400ing new Anthropic clients** — no injected default temperature;
   strip sampling under API version `2026-10-21` (row 179).
3. **Make the fenced judge hop visible and clearable** — doctor/ready/reset
   (row 173).
4. **Bill cache writes like the invoice** — OpenAI TTL rates (row 174) and
   shrink enforcement blast radius via user profiles (row 175).
5. **Finish FinOps on the console** — spend export download (row 180) plus
   invalidate tenancy (row 176).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-21 pm (LiteLLM compromise + Anthropic API-version footgun)** —
  Outward: LiteLLM 1.107.0 PyPI/Docker compromise (infostealer + RAT;
  quarantined) — floor stays 1.106.2; Anthropic API version `2026-10-21`
  removes sampling params; Ollama 0.40.8-rc0 Flint. Filed rows 178–182:
  compromise advisory, Anthropic version-safe sampling, console spend
  export, `between_tools` soft_warning/Prom, Flint L4 recipe. Marked row
  171 Superseded. Morning rows 173–177 remain open.

- **2026-10-21 (breaker truth, invoice-true cache billing, user-profile
  blast radius)** — Marked rows 161–170 Shipped; filed rows 173–177.
  Outward: LiteLLM GA floor 1.106.2; Ollama 0.40.7; OpenAI 12h prompt
  cache; Anthropic user profiles.

- **2026-10-20 (finish the knobs + evening speed-keyed ops)** — Filed rows
  163–172. Outward: LiteLLM 1.106.0 GA; 1.107.0-rc.2 watchables; Anthropic
  `thinking.types.between_tools`.

- **2026-10-19 → 08-28** — Condensed: decisions-upstream depth; fast-mode
  cache truth; `resultType`/egress/billing waves; lifecycle/tenancy/DR;
  LiteLLM 1.104–1.106; Apache 2.0; this PRD's creation.
