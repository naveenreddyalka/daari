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

## Where daari stands (verified in-tree, 2026-10-07 evening)

**Loop velocity.** Morning rows 44–48 (Decisions facade, MCP OAuth
scope/revoke, new-surface hardening, web-ui admin plane, Responses multi-agent
honesty) plus `/mcp/proxy` cost headers and hot-reload remain the open
execution stack. Catalog/pricing for sonnet-5-5 / grok-4.7 / opus-5-5 and MCP
OAuth mint audit are on `main`.

**Outward.** **Vercel AI Gateway added OpenAI-compatible `/v1/decisions` today
(7 Oct)** with slug `openai/gpt-6-luna-decisions` (distinct from the LM
`openai/gpt-6-luna`). OpenAI Decisions beta pricing clarified: **$0.10 / 1M
input, $0 output / $0 cache on the Decisions path** — not the chat rate card.
LiteLLM published **v1.106.0-dev.1** (M365 Graph MCP catalog, scoped-SQL
tracing); stable bar remains **1.104.0 GA** (1.105 still RC). Anthropic
`capabilities.thinking.types.disabled` (5 Oct) still absent from daari's
Anthropic `/v1/models` cards. Ollama 0.40.0 / Portkey / Kong / OpenRouter flat
vs morning.

**Inward theme: Decisions FinOps honesty + catalog/ops depth.** Code audit:
Anthropic model cards emit `line` but no `capabilities` object; age-encrypt
backup has no round-trip test (openssl covered); Grafana dashboard lacks
panels for shipped `daari_decision_classifier_*` series; pricing is
path-agnostic so a Decisions facade would over-bill if it reused chat
`gpt-6-luna` rates; Vercel-style `*-decisions` model aliases have no
normalizer.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 49 | Anthropic `capabilities.thinking.types.disabled` on native `/v1/models` | 3 | 1 | Anthropic Models API (5 Oct) | On-box catalog honesty for Claude clients | Filed [#1481](https://github.com/naveenreddyalka/daari/issues/1481) |
| 50 | age-encrypt backup create/restore round-trip test | 3 | 1 | — (ops testability) | Prove both encrypt backends before restore day | Filed [#1482](https://github.com/naveenreddyalka/daari/issues/1482) |
| 51 | Grafana panels for decision classifier Prom series | 3 | 1 | LiteLLM / Kong decision dashboards | Stock dashboard proves on-box classifier SLO | Filed [#1483](https://github.com/naveenreddyalka/daari/issues/1483) |
| 52 | Decisions-path input-only pricing for gpt-6-luna (≠ chat rates) | 4 | 2 | OpenAI Decisions beta rate card | Cost-true FinOps when frontier Decisions is used | Filed [#1484](https://github.com/naveenreddyalka/daari/issues/1484) |
| 53 | Normalize `gpt-6-luna-decisions` / `openai/gpt-6-luna-decisions` aliases | 3 | 1 | Vercel AI Gateway Decisions (7 Oct) | One localhost URL accepts OpenAI + gateway slugs | Filed [#1485](https://github.com/naveenreddyalka/daari/issues/1485) |
| 44 | OpenAI-compatible `/v1/decisions` on local decision models + gpt-6-luna fallback | 5 | 2 | OpenAI Decisions beta; Vercel AI Gateway; Portkey/Kong Jev | Typed judgments on-box at $0, frontier only on miss | Filed (morning) |
| 45 | MCP OAuth AS: scope enforcement + RFC 7009 revocation | 4 | 2 | LiteLLM 1.103 token-exchange; Kong Token Vault | On-box revoke/scope check = zero network hops | Filed (morning) |
| 46 | OTel spans + guardrails + retry on `/mcp/proxy` and `/v1/systemone` | 4 | 2 | Kong W3C trace on MCP; Portkey guardrails | Local policy checks add near-zero latency | Filed (morning) |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM proxy admin UI | Same-box console, no SaaS, reuses existing stores | Filed (morning) |
| 48 | Responses multi-agent beta fields forwarded or honest 400 | 3 | 2 | OpenAI gpt-6.1-sol multi-agent beta | Transparent delegation passthrough with budgets intact | Filed (morning) |
| 37 | Web-ui hardening: escape DOM, CSP, no localStorage keys | 4 | 3 | LiteLLM proxy UI | Static page — escaping + CSP are cheap | Shipped |
| 38 | OCR Prometheus modality + output guardrails + OTel | 4 | 2 | Kong per-modality costs | Local OCR pitch needs honest FinOps + redaction | Shipped |
| 39 | claude-sonnet-5-5 pricing / capabilities / param compat | 4 | 1 | LiteLLM 1.105 RC day-one catalog | Cost-true L6 when agents already pick the new ID | Shipped |
| 40 | Anthropic Models API `line` on native `/v1/models` | 3 | 1 | Anthropic Models API (1 Oct) | Local catalog parity for Claude-native clients | Shipped |
| 41 | Decision classifier Prometheus latency + outcome series | 4 | 2 | LiteLLM / Kong decision metrics | Prove on-box classifier SLO vs hosted Jev | Shipped |
| 42 | Watchdog fatal-config classifier + stop KeepAlive spam | 4 | 2 | — (ops honesty) | Autonomous loop must not file daemon-unreachable forever | Shipped |
| 43 | compact_to_fit counts images/audio; protect image-only turns | 3 | 2 | LiteLLM multimodal compact | FinOps + vision context honesty before L6 | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; group-scoped priority; stdio MCP; M365 catalog; Skills API; FIPS/distroless; HIPAA BAA program | 2–4 | 3–5 | Portkey / Kong / LiteLLM 1.104–1.106 / OpenAI | Demand-triggered | Watch |

Shipped since the 2026-10-06 evening scan — do not re-file: web-ui
escape/CSP/key-storage; OCR modality/guardrails/OTel; claude-sonnet-5-5,
grok-4.7, claude-opus-5-5 pricing/compat; Anthropic `line` on `/v1/models`;
classifier Prometheus series; watchdog fatal-config classifier; compact
images/audio estimates; MCP OAuth mint audit events. Earlier shipped (do not
re-file): master-key config gate; gpt-6.1-sol pricing; systemone images +
rate family; compact-to-fit + MCP grant fail-closed full stacks; OBO;
refuse-weak-master-key; decision classifier; `/v1/ocr`; `/v1/systemone`;
MCP registry/proxy/OAuth mint; watchdog dedupe + hatch docs.

Watch rows (audit-verified 2026-10-07 evening — file on trigger): LiteLLM
1.105 RC → GA and 1.106-dev M365 MCP catalog + scoped-SQL / Lens agent
traces (file at GA); gpt-6-luna Decisions schema drift while the beta
hardens; `GET /v1/mcp/registry.json` auth-open by design; OpenAI in-product
HIPAA BAA (compliance non-goal until buyer demand); vLLM Semantic Router
Decision/Vela 2.0 open routing models (demand-triggered). Verified fine —
don't re-audit: hosted Responses tool types 400 honestly; `/mcp/proxy` +
systemone use pooled httpx; OCR has `post_l6` retry + output policy + span;
MCP OAuth enforces `exp` and audits mint/deny; web-ui binds 127.0.0.1 and
escapes DOM; openssl backup encrypt round-trip tested; Anthropic `line` on
catalog.

---

## Path to enterprise-grade — next 5 milestones

1. **Local-first Decisions API** — `/v1/decisions` facade (row 44) plus
   input-only FinOps (row 52) and gateway model aliases (row 53) so OpenAI-
   and Vercel-shaped clients bill correctly on-box.
2. **MCP OAuth lifecycle** — scope enforcement + revocation (row 45) so the
   on-box AS is credible against LiteLLM token-exchange and Kong Token Vault.
3. **New-surface hardening parity** — spans/guardrails/retry on `/mcp/proxy`
   and `/v1/systemone` (row 46), closing the gap to the OCR treatment.
4. **Operator console + classifier visibility** — web-ui admin read plane
   (row 47) and Grafana classifier panels (row 51); LiteLLM's admin UI +
   decision metrics are sticky adoption levers.
5. **Catalog / client honesty** — Anthropic `thinking.types.disabled` (row
   49), multi-agent beta passthrough (row 48), then hot-reload (row 6) and
   the parked Messages tool allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-07 evening (Decisions FinOps + catalog/ops depth)** — Outward:
  Vercel AI Gateway `/v1/decisions` (7 Oct) with `openai/gpt-6-luna-decisions`;
  OpenAI Decisions input-only pricing clarified; LiteLLM 1.106.0-dev.1
  published (stable bar still 1.104 GA). Inward: filed rows 49–53 —
  Anthropic `thinking.types.disabled`, age-encrypt backup test, Grafana
  classifier panels, Decisions-path input-only pricing, Decisions model
  aliases. Morning rows 44–48 remain the active Decisions/lifecycle stack.

- **2026-10-07 (decisions surface + lifecycle depth)** — Rows 37–43 all
  Shipped within a day (plus grok-4.7 / claude-opus-5-5 pricing and MCP OAuth
  mint audit). Outward: OpenAI Decisions API beta with gpt-6-luna (6 Oct);
  Ollama 0.40.0 stable (MLX default); Anthropic `thinking.types.disabled`
  Models field; LiteLLM bar unchanged at 1.104 GA. Inward: filed rows 44–48
  — local-first `/v1/decisions`, MCP OAuth scope/revocation, new-surface
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
