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

## Where daari stands (verified in-tree, 2026-10-06 evening)

**Loop velocity.** Morning admin-plane + new-surface batch drained in hours:
master-key gate on SSO-off config writes, gpt-6.1-sol pricing/compat, and
systemone Clef `images` + `systemone` rate family are on `main`. Still open:
web-ui escape/CSP/key-storage, OCR Prom modality + guardrails/OTel. Hot-reload
`config.yaml` stays in flight; Messages `mcp_servers` tool allowlist stays parked.

**Outward.** LiteLLM **v1.104.0 GA** remains the stable bar; **v1.105.0-rc.1**
(4 Oct) still watch-only but day-ones Claude Sonnet 5.5, Grok 4.7, Lens/Agent
Traces, and `litellm.agent()`. **Kong 2.2.0** / **Portkey v2.27.0** /
**Ollama 0.35.1** unchanged since morning. **Provider mover now:** Anthropic
**claude-sonnet-5-5** (28 Sep, $2/$10, adaptive thinking; non-default
temperature → 400) is absent from daari's price/compat tables; Models API
`line` (1 Oct) still missing on native `/v1/models`.

**Inward theme: October catalog truth + classifier/watchdog ops honesty.**
Code audit confirmed: no `claude-sonnet-5-5` in `_DEFAULT_MODEL_PRICES` /
param_compat; `anthropic_model_cards()` omits `line`; decision classifier has
trace-only observability; compact_to_fit `estimate_tokens` ignores
`images`/`audio` and can drop image-only turns; local watchdog still
KeepAlive-loops on fatal master_key refuse (two open regression trackers).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 39 | claude-sonnet-5-5 pricing / capabilities / param compat | 4 | 1 | LiteLLM 1.105 RC day-one catalog | Cost-true L6 when agents already pick the new ID | Filed [#1450](https://github.com/naveenreddyalka/daari/issues/1450) |
| 40 | Anthropic Models API `line` on native `/v1/models` | 3 | 1 | Anthropic Models API (1 Oct) | Local catalog parity for Claude-native clients | Filed [#1451](https://github.com/naveenreddyalka/daari/issues/1451) |
| 41 | Decision classifier Prometheus latency + outcome series | 4 | 2 | LiteLLM / Kong decision metrics | Prove on-box classifier SLO vs hosted Jev | Filed [#1452](https://github.com/naveenreddyalka/daari/issues/1452) |
| 42 | Watchdog fatal-config classifier + stop KeepAlive spam | 4 | 2 | — (ops honesty) | Autonomous loop must not file daemon-unreachable forever | Filed [#1453](https://github.com/naveenreddyalka/daari/issues/1453) |
| 43 | compact_to_fit counts images/audio; protect image-only turns | 3 | 2 | LiteLLM multimodal compact | FinOps + vision context honesty before L6 | Filed [#1454](https://github.com/naveenreddyalka/daari/issues/1454) |
| 37 | Web-ui hardening: escape DOM, CSP, no localStorage keys | 4 | 3 | LiteLLM proxy UI | Static page — escaping + CSP are cheap | Open [#1444](https://github.com/naveenreddyalka/daari/issues/1444) |
| 38 | OCR modality mislabeled as chat in Prometheus; no guardrails/OTel | 4 | 2 | Kong per-modality costs | Local OCR pitch needs honest FinOps + redaction | Open [#1445](https://github.com/naveenreddyalka/daari/issues/1445) |
| 34 | Master-key gate on `/v1/daari/config` writes when SSO off | 5 | 2 | LiteLLM 1.104 master-key admin routes | Local check; `master_key_matches` already in SSO-on path | Shipped |
| 35 | gpt-6.1-sol pricing / capabilities / param compat | 4 | 1 | LiteLLM price map cadence | Cost-true local-vs-frontier escalation | Shipped |
| 36 | `/v1/systemone` multimodal `images` + dedicated rate family | 4 | 1 | Ollama 0.35.1 native | Decision models stay on-box vs hosted Jev | Shipped |
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
| 8 | Full DCR; A2A; Realtime/WS; group-scoped priority; stdio MCP; M365 catalog; Skills API; FIPS/distroless images | 2–4 | 3–5 | Portkey / Kong 2.2.0 / LiteLLM 1.104–1.105 | Demand-triggered | Watch |

Shipped since morning 2026-10-06 scan — do not re-file: master-key config
gate; gpt-6.1-sol pricing/compat; systemone images + rate family. Earlier
shipped (do not re-file): web-ui compact/MCP stats; structured_json_logs
ownership/doctor; savings-report compact pin; compare-litellm 1.105 RC note;
compact-to-fit + MCP grant fail-closed full stacks; OBO; refuse-weak-master-key;
decision classifier; `/v1/ocr`; `/v1/systemone`; MCP registry/proxy/OAuth mint;
watchdog dedupe + hatch docs.

Watch rows (audit-verified 2026-10-06 evening — file on trigger): MCP OAuth
mint lacks `audit_log` events + rotation/revoke; `/mcp/proxy` lacks cost
headers + guardrails; `GET /v1/mcp/registry.json` auth-open by design (doctor
tip exists); gpt-6.1-sol Responses multi-agent beta; Portkey-style identified
502 for unreachable MCP egress (chat path returns in-band tool failure by
design); Claude Opus 5.5 / Grok 4.7 catalog entries when LiteLLM 1.105 GA
lands. Verified fine — don't re-audit: OCR has `ocr` rate family + budgets +
`post_l6`; systemone meters spend/usage + Prom `systemone` modality + cost
headers + images forward; MCP OAuth enforces `exp`; compact protects
system/tool pairs, fail-closed, no L0/L1 key pollution; classifier degrades to
heuristic + `tier_override` bypass; web-ui binds 127.0.0.1 by default;
SSO-off config writes require master key.

---

## Path to enterprise-grade — next 5 milestones

1. **October frontier catalog truth** — claude-sonnet-5-5 pricing/compat
   (row 39) + Anthropic `line` on `/v1/models` (row 40). Agents already
   request the new Sonnet ID; unpriced L6 breaks the cost pitch.
2. **Admin-plane trust (finish)** — web-ui escape/CSP/key-handling (row 37);
   master-key config gate shipped this morning.
3. **Classifier + compact honesty** — Prometheus latency/outcome (row 41) and
   multimodal compact estimates (row 43) so local decision/FinOps paths are
   measurable and safe.
4. **Modality observability** — OCR mislabel + guardrails + OTel (row 38).
5. **Loop reliability + live config** — watchdog fatal-config classifier
   (row 42), then hot-reload (row 6) and parked Messages tool allowlist
   (row 7) once the loop frees up.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds) stay deferred until buyer demand.

---

## Changelog

- **2026-10-06 evening (catalog + classifier/watchdog ops)** — Morning rows
  34–36 marked Shipped (config master-key, gpt-6.1-sol, systemone images).
  Outward: LiteLLM 1.105 RC day-ones Claude Sonnet 5.5 (still absent in-tree);
  Kong/Portkey/Ollama flat. Inward: filed five issues (rows 39–43) for
  sonnet-5-5 catalog, Anthropic `line`, classifier Prom series, watchdog
  fatal-config backoff, and multimodal compact estimates. Web-ui + OCR
  hardening remain open from morning.

- **2026-10-06 (admin-plane + new-surface governance)** — Outward: Kong 2.2.0,
  Portkey v2.27.0, Ollama 0.35.1 multimodal decision models, OpenAI
  gpt-6.1-sol, Anthropic `line`; LiteLLM bar unchanged at 1.104 GA. Filed
  rows 34–38; three shipped same day.

- **2026-10-05 (operate-gates + FinOps surface shipped)** — Grafana compact,
  grant counter, initialize refuse, token-drop stats, compare-litellm 1.104
  marked Shipped; FinOps/container-ops refill drained same-day.

- **2026-10-04 → 08-28** — Condensed: LiteLLM 1.104 GA + operate-gates;
  OBO + refuse-weak-key + classifier; decision models + MCP OAuth; structured
  outputs; client honesty; MCP ops; Apache 2.0; this PRD's creation.
