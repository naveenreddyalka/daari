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

## Where daari stands (verified in-tree, 2026-10-19)

**Loop velocity.** The entire 10-18 board (rows 136–149, three scans) merged
within 24h — streamed fast degrade, fence-aware pins, `:cloud` catalog
markers, both proxy `resultType` stamps, and the configurable systemone
upstream (#1778 → PR #1790) are all on main. The loop self-refilled with
three systemone follow-ups (rows 150–152). `agent:working` rows 6/62–63/
65–67 unchanged.

**Outward.** Fully flat since the 10-18 scans: LiteLLM 1.106.0 GA /
1.107.0-rc.1, vLLM 0.32.0, Ollama 0.40.7-rc0, Portkey v2.29.0, OpenRouter
(Oct 9), Anthropic (10-15), OpenAI (10-16 prompt-to-voice, non-goal).
**Kong Gateway 3.16.0.1 (10-12):** `ai-a2a-proxy` adds A2A v1.0 wire-format
and `ai-proxy-advanced` gains prompt cache-control mappings + byte-preserving
forwards — A2A stays a demand-gated watch. Claude Code 2.1.303 is patch-only.

**Inward theme: depth behind the configurable decisions upstream.** The
new `systemone.base_url` hop cannot be deployed by the Helm chart, carries
no auth to the upstream, and has retry but no breaker. And the fast-mode
wave missed the cache layer: `speed` is absent from the L0 fingerprint, so
fast and standard requests share one cache entry.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 153 | L0 cache fingerprint includes Anthropic `speed` (today fast/standard share an entry) | 4 | 1 | LiteLLM cache keying | On-box cache truth backs fast-mode bill-back | Filed [#1798](https://github.com/naveenreddyalka/daari/issues/1798) |
| 154 | Helm `systemone.baseUrl` knob + env + NetworkPolicy egress | 4 | 2 | LiteLLM/vLLM charts | The vLLM decisions box is reachable from a governed cluster | Filed [#1799](https://github.com/naveenreddyalka/daari/issues/1799) |
| 155 | `systemone.api_key` Bearer on the configured upstream (all four call sites + doctor probe) | 4 | 2 | vLLM `--api-key` / LiteLLM provider creds | Shared on-prem judge boxes need auth without a sidecar | Filed [#1800](https://github.com/naveenreddyalka/daari/issues/1800) |
| 156 | Circuit breaker on the systemone upstream + shared pool/retry on the classifier hop | 4 | 3 | Kong/Envoy breakers | Fail-fast keeps the per-request judge hop credible | Filed [#1801](https://github.com/naveenreddyalka/daari/issues/1801) |
| 157 | Spend export `--model`/`--usage-speed` filters + Grafana cloud/fast panels | 3 | 2 | Portkey spend UI | Fast-vs-standard and local-vs-cloud FinOps on-box | Filed [#1802](https://github.com/naveenreddyalka/daari/issues/1802) |
| 150 | Doctor names the resolved systemone root on the classifier check | 2 | 1 | — (ops honesty) | Doctor says which box the hop really hits | Open [#1793](https://github.com/naveenreddyalka/daari/issues/1793) |
| 151 | `daari_meta` labels the resolved systemone executor (not hardcoded ollama) | 3 | 1 | — (response honesty) | Clients see which upstream answered | Open [#1794](https://github.com/naveenreddyalka/daari/issues/1794) |
| 152 | Upstream request ids on systemone HTTP failures | 3 | 1 | LiteLLM failure logs | Provider tickets cite the id on-box | Open [#1795](https://github.com/naveenreddyalka/daari/issues/1795) |
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
| 8 | Full DCR; A2A (Kong 3.16.0.1 now speaks v1.0); Realtime/WS (incl. GPT-Live Decisions); stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): streamed fast-mode 429/529 degrade;
fence-aware session pins; `:cloud` remote markers on `/api/tags`, `/api/show`,
and model cards; `resultType` on JSON-RPC `tools/call`, OpenAPI proxy, and
`tasks/get`; configurable systemone upstream for OpenAI-compatible backends
(+ doctor catalog probe #1792); trailing empty user turns; image/document
`count_tokens`; web-search call fees; upstream request ids on frontier
failures; fast-mode rate-limit header copy (Messages + chat); adaptive
thinking key strip; `speed`-ignored warning; compare-litellm 1.106.0 GA floor.

Watch rows (do not file yet): systemone multi-upstream / opt-in Ollama
fallback when the explicit base is down (file on fleet demand); a gateway
integration-flow case for the configurable systemone override (unit
MockTransport only today — fold into the next test audit); gzip compression
Prom metrics (ratio/CPU — operator ask); `schema_ok` Prometheus gauge +
web-ui banner (today it is `/ready` + doctor only); budget threshold
webhooks: ISO `reset_at` parity with the report path + model-budget
(`model_max_budget`) alert coverage; events web-ui `key_id`/`kind` filters +
payload column (API already returns them); `CONFIGURE_CLIENTS` first-wave
tuple lags the registry (trivial, fold into the next recipe); cursor-agent
CLI configure (distinct from the Cursor IDE recipe); `migrate --downgrade`
(demand-triggered); Responses background completion webhooks + wider
`include` allowlist (one include today, poll-only); per-user request-count
RPD (USD caps only); SCIM + multi-issuer/audience SSO (multi-JWKS yes,
single issuer/audience str); Prometheus exemplars + `gen_ai.agent.*` spans +
PG request-log concurrency/soak tests; Portkey v2.29 JWT claims→metadata
conditional routing (buyer ask); LiteLLM 1.107 GA watchables
(`agent_access_default_deny`); native-API refusal recipes beyond Gemini CLI
as such clients appear; vLLM 0.32 Responses reasoning stream event renames
(no in-tree impact — `kind: openai` backends speak chat-completions);
Kong `ai-proxy-advanced` byte-preserving forwards for provider prompt
caches (daari builds payloads deterministically — re-check if provider
cache-hit complaints appear); Anthropic Compliance API user-preferences
export + OpenAI GPT-Live incl. prompt-to-voice (non-goals).

Verified fine this run — don't re-audit: configurable `base_url` honored on
the systemone facade, local decisions, guardrail predicates, and classifier;
doctor probes the configured catalog via `/v1/models` and names the explicit
base; shared pooled client + `run_upstream` retry on the facade and
decisions paths; `Idempotency-Key` on both decisions routes; `:cloud` rows
in metered spend SQL; scheme-only URL validation on `systemone.base_url`
(private addresses intentionally allowed — lab GPUs); lockout unlock verb
present on CLI/API/web-ui; ASR/TTS/Ollama Helm knobs coherent; `speed`
parsed on both ingress shapes and gated before egress (the gap is cache
keying only, row 153).

---

## Path to enterprise-grade — next 5 milestones

1. **Cache truth for fast mode** — include `speed` in the L0 fingerprint
   (row 153) so the cache layer stops conflating fast and standard
   responses the rest of the stack already bills and degrades honestly.
2. **Deployable decisions upstream** — Helm knob + env + NetworkPolicy
   egress (row 154) and upstream Bearer auth (row 155) make the vLLM
   `/v1/systemone` story real in a governed cluster, not just on a laptop.
3. **Fail-fast judge hop** — a breaker on the systemone upstream and a
   pooled, retry-aware classifier hop (row 156) keep per-request decision
   latency credible when the judge box is down.
4. **FinOps slices for the new spend dimensions** — `--model` /
   `--usage-speed` export filters and Grafana cloud/fast panels (row 157)
   turn recorded `:cloud` and fast-mode rows into operator answers.
5. **Systemone observability follow-ups** — resolved-root doctor naming,
   executor-true `daari_meta`, and upstream request ids (rows 150–152)
   land from today's refill; admin-plane rows 62–67 stay with their
   `agent:working` sessions.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-19 (depth behind the configurable decisions upstream + fast-mode
  cache truth)** — Marked rows 136–149 Shipped (the whole 10-18 board merged
  in <24h, incl. the systemone upstream #1778/PR #1790). Added rows 150–152
  for the loop's same-day systemone refill (#1793–#1795). Filed rows
  153–157: L0 `speed` cache fingerprint, Helm/NetworkPolicy knobs for
  `systemone.base_url`, upstream `api_key` Bearer, systemone circuit
  breaker + pooled classifier hop, and spend export/Grafana slices for
  `:cloud` and fast-mode. Outward flat: LiteLLM 1.106.0 GA, vLLM 0.32.0,
  Ollama 0.40.7-rc0, Portkey v2.29.0, OpenRouter, Anthropic, OpenAI
  unchanged; noted Kong Gateway 3.16.0.1 (`ai-a2a-proxy` A2A v1.0,
  byte-preserving `ai-proxy-advanced` forwards); Claude Code 2.1.303
  patch-only.

- **2026-10-18 third scan (stream-path fast mode, egress truth, vLLM 0.32)**
  — Corrected the outward board: vLLM 0.32.0 (10-18) serves
  `POST /v1/systemone` by default — the earlier scans still pinned 0.31.0.
  Filed rows 145–149: streamed fast-mode degrade, fence-aware session
  pins, `:cloud` catalog markers, OpenAPI proxy `resultType`, and a
  configurable systemone upstream for OpenAI-compatible backends.
  LiteLLM 1.106.0 GA, Ollama 0.40.7-rc0, Portkey v2.29.0, Kong 2.2.0,
  OpenRouter, and Anthropic (10-15) unchanged since the evening scan.

- **2026-10-18 evening (replay, count, and ledger honesty)** — Marked
  rows 136 and 139 Shipped (`tools/call` `resultType`, compare-litellm
  1.106.0 GA floor). Filed rows 140–144: trailing empty user turns,
  image/document `count_tokens`, web-search call fees, upstream request
  ids on frontier HTTP failures, and a `speed` warning when L6 is not
  Anthropic. Outward: LiteLLM 1.107.0-rc.1 still prerelease; Ollama
  0.40.7-rc0, Portkey, Kong 2.2.0, vLLM 0.31.0, and OpenRouter unchanged.

- **2026-10-18 (1.106 GA, call-result resultType, fast-mode headers)** —
  Marked rows 123–135 Shipped (egress fences, stream billing, 529 degrade,
  events/lockout surfaces, catalog/doctor/ready honesty). Filed rows
  136–139: `tools/call` `resultType`, Anthropic fast-mode rate-limit header
  copy, adaptive thinking key strip, compare-litellm 1.106.0 GA.
  Outward: LiteLLM 1.106.0 GA and 1.107.0-rc.1; Ollama 0.40.7-rc0 left on
  watch. Anthropic, Portkey, Kong, vLLM, and OpenRouter unchanged.

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
