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

## Where daari stands (verified in-tree, 2026-10-07)

**Loop velocity.** The entire 2026-10-06 evening table (rows 37–43) drained in
under a day: web-ui escape/CSP/key-storage, OCR Prom modality + output
guardrails + OTel, claude-sonnet-5-5, Anthropic `line` on `/v1/models`,
classifier Prometheus series, watchdog fatal-config classifier, and multimodal
compact estimates are all on `main` — plus grok-4.7 and claude-opus-5-5
pricing and MCP OAuth mint audit events. Hot-reload `config.yaml` stays in
flight; Messages `mcp_servers` tool allowlist stays parked; `/mcp/proxy` cost
headers are queued in the backlog.

**Outward.** **OpenAI shipped the Decisions API beta with `gpt-6-luna`
(6 Oct)** — typed text/image judgments, now the third competitor decisions
surface after Portkey v2.25.0 (TypeSafe Jev) and Kong 2.2.0. **Ollama v0.40.0
went stable** (MLX default runtime on Apple Silicon, including decision models
and an MLX embedding model — runtime-only, facade unaffected). Anthropic added
`capabilities.thinking.types.disabled` to the Models API (5 Oct). LiteLLM bar
stays **v1.104.0 GA** (1.105.0-rc.1 / 1.106.0-dev.1 add M365 MCP catalog +
scoped-SQL tracing — watch). Portkey v2.27.0 / Kong 2.2.0 / OpenRouter (08-19)
/ MCP blog (08-22) flat.

**Inward theme: decisions surface + lifecycle depth on the new stacks.**
Code audit confirmed: no `/v1/decisions` and no `gpt-6-luna` pricing; the MCP
OAuth AS mints tokens with unvalidated scopes, never checks the scope claim on
verify, and has no revocation; `/mcp/proxy` and `/v1/systemone` lack OTel
spans, guardrails, and retry (OCR has all three on output); the web-ui is
observability-only (keys/teams/spend have no HTTP read plane); Responses
silently drops gpt-6.1-sol multi-agent beta fields.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 44 | OpenAI-compatible `/v1/decisions` on local decision models + gpt-6-luna fallback | 5 | 2 | OpenAI Decisions beta (6 Oct); Portkey/Kong Jev | Typed judgments on-box at $0, frontier only on miss | Filed [#1474](https://github.com/naveenreddyalka/daari/issues/1474) |
| 45 | MCP OAuth AS: scope enforcement + RFC 7009 revocation | 4 | 2 | LiteLLM 1.103 token-exchange; Kong Token Vault | On-box revoke/scope check = zero network hops | Filed [#1475](https://github.com/naveenreddyalka/daari/issues/1475) |
| 46 | OTel spans + guardrails + retry on `/mcp/proxy` and `/v1/systemone` | 4 | 2 | Kong W3C trace on MCP; Portkey guardrails on decisions `state` | Local policy checks add near-zero latency | Filed [#1476](https://github.com/naveenreddyalka/daari/issues/1476) |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM proxy admin UI | Same-box console, no SaaS, reuses existing stores | Filed [#1477](https://github.com/naveenreddyalka/daari/issues/1477) |
| 48 | Responses multi-agent beta fields forwarded or honest 400 | 3 | 2 | OpenAI gpt-6.1-sol multi-agent beta | Transparent delegation passthrough with budgets intact | Filed [#1478](https://github.com/naveenreddyalka/daari/issues/1478) |
| 37 | Web-ui hardening: escape DOM, CSP, no localStorage keys | 4 | 3 | LiteLLM proxy UI | Static page — escaping + CSP are cheap | Shipped |
| 38 | OCR Prometheus modality + output guardrails + OTel | 4 | 2 | Kong per-modality costs | Local OCR pitch needs honest FinOps + redaction | Shipped |
| 39 | claude-sonnet-5-5 pricing / capabilities / param compat | 4 | 1 | LiteLLM 1.105 RC day-one catalog | Cost-true L6 when agents already pick the new ID | Shipped |
| 40 | Anthropic Models API `line` on native `/v1/models` | 3 | 1 | Anthropic Models API (1 Oct) | Local catalog parity for Claude-native clients | Shipped |
| 41 | Decision classifier Prometheus latency + outcome series | 4 | 2 | LiteLLM / Kong decision metrics | Prove on-box classifier SLO vs hosted Jev | Shipped |
| 42 | Watchdog fatal-config classifier + stop KeepAlive spam | 4 | 2 | — (ops honesty) | Autonomous loop must not file daemon-unreachable forever | Shipped |
| 43 | compact_to_fit counts images/audio; protect image-only turns | 3 | 2 | LiteLLM multimodal compact | FinOps + vision context honesty before L6 | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
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
| 8 | Full DCR; A2A; Realtime/WS; group-scoped priority; stdio MCP; M365 catalog; Skills API; FIPS/distroless; HIPAA BAA program | 2–4 | 3–5 | Portkey / Kong 2.2.0 / LiteLLM 1.104–1.106 / OpenAI | Demand-triggered | Watch |

Shipped since the 2026-10-06 evening scan — do not re-file: web-ui
escape/CSP/key-storage; OCR modality/guardrails/OTel; claude-sonnet-5-5,
grok-4.7, claude-opus-5-5 pricing/compat; Anthropic `line` on `/v1/models`;
classifier Prometheus series; watchdog fatal-config classifier; compact
images/audio estimates; MCP OAuth mint audit events. Earlier shipped (do not
re-file): master-key config gate; gpt-6.1-sol pricing; systemone images +
rate family; compact-to-fit + MCP grant fail-closed full stacks; OBO;
refuse-weak-master-key; decision classifier; `/v1/ocr`; `/v1/systemone`;
MCP registry/proxy/OAuth mint; watchdog dedupe + hatch docs.

Watch rows (audit-verified 2026-10-07 — file on trigger): Anthropic
`capabilities.thinking.types.disabled` on native `/v1/models` (P3 parity —
fold into next catalog sweep); `GET /v1/mcp/registry.json` auth-open by
design; gpt-6-luna Decisions schema drift while the beta hardens; age-encrypt
backup restore has no test (openssl round-trip tested — fold into next test
audit); LiteLLM 1.105/1.106 M365 MCP catalog + scoped-SQL tracing (file at
GA); OpenAI in-product HIPAA BAA (compliance non-goal until buyer demand);
Ollama 0.40.0 MLX runtime (resolved — runtime-only, facade unaffected).
Verified fine — don't re-audit: hosted Responses tool types 400 honestly;
`/mcp/proxy` + systemone use pooled httpx; OCR has `post_l6` retry + output
policy + span; MCP OAuth enforces `exp` and audits mint/deny; web-ui binds
127.0.0.1 and escapes DOM; watchdog classifier has unit tests.

---

## Path to enterprise-grade — next 5 milestones

1. **Local-first Decisions API** — `/v1/decisions` facade on local decision
   models with gpt-6-luna fallback + pricing (row 44). OpenAI just
   standardized the shape; daari can be the only local-first implementation.
2. **MCP OAuth lifecycle** — scope enforcement + revocation (row 45) so the
   on-box AS is credible against LiteLLM token-exchange and Kong Token Vault.
3. **New-surface hardening parity** — spans/guardrails/retry on `/mcp/proxy`
   and `/v1/systemone` (row 46), closing the gap to the OCR treatment.
4. **Operator console** — read-only keys/teams/spend plane in the web-ui
   (row 47); LiteLLM's admin UI is its stickiest adoption lever.
5. **Agent-era client honesty** — multi-agent beta passthrough (row 48), then
   hot-reload (row 6) and the parked Messages tool allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-07 (decisions surface + lifecycle depth)** — Rows 37–43 all
  Shipped within a day (plus grok-4.7 / claude-opus-5-5 pricing and MCP OAuth
  mint audit); this refresh also covers the ask in issue #1470. Outward:
  OpenAI Decisions API beta with gpt-6-luna (6 Oct); Ollama 0.40.0 stable
  (MLX default); Anthropic `thinking.types.disabled` Models field; LiteLLM
  bar unchanged at 1.104 GA. Inward: filed rows 44–48 — local-first
  `/v1/decisions`, MCP OAuth scope/revocation, new-surface
  spans/guardrails/retry, web-ui admin read plane, Responses multi-agent
  honesty.

- **2026-10-06 evening (catalog + classifier/watchdog ops)** — Filed rows
  39–43 (sonnet-5-5 catalog, Anthropic `line`, classifier Prom series,
  watchdog fatal-config backoff, multimodal compact estimates); rows 34–36
  marked Shipped.

- **2026-10-06 (admin-plane + new-surface governance)** — Kong 2.2.0, Portkey
  v2.27.0, Ollama 0.35.1, gpt-6.1-sol, Anthropic `line`. Filed rows 34–38;
  three shipped same day.

- **2026-10-05 → 08-28** — Condensed: operate-gates + FinOps surface;
  LiteLLM 1.104 GA; OBO + refuse-weak-key + classifier; decision models +
  MCP OAuth; structured outputs; client honesty; MCP ops; Apache 2.0; this
  PRD's creation.
