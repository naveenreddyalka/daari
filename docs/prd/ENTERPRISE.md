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

## Where daari stands (verified in-tree, 2026-10-06)

**Loop velocity.** The whole 2026-10-05 FinOps/container-ops table (web-ui
stats cards, `structured_json_logs` ownership + doctor tip, savings-report pin,
LiteLLM 1.105 RC note) shipped within hours. Operate-gates for compact-to-fit
and MCP grant fail-closed are fully on `main`. Hot-reload `config.yaml` stays
in flight; per-key tool-name allowlists for Messages `mcp_servers` stay parked.

**Outward.** LiteLLM **v1.104.0 GA** remains the stable bar; v1.105.0-rc.1
watch-only. **Kong 2.2.0** (30 Sep): FIPS 140-3 + distroless images, TypeSafe
Jev decision models, Token Vault MCP creds, OpenAI/Anthropic Skills API
passthrough, CP/DP version-skew sync guard. **Portkey v2.27.0**: MCP
unreachable → identified 502, PII redaction on embeddings, Decisions via
OpenRouter. **Ollama 0.35.1 stable**: multimodal Clef decision models
(`images` on `/v1/systemone`), Modelfile `CAPABILITY`, `decision` capability
reporting. **Provider side is the mover:** OpenAI **gpt-6.1-sol** (29 Sep,
$2/$10, cached $0.10) is 5× cheaper than gpt-6-astra and absent from daari's
pricing table; Anthropic Models API added a `line` field (1 Oct). vLLM 0.31.0
engine-internal; OpenRouter (08-19) and MCP blog (08-22) flat.

**Inward theme: admin-plane trust + new-surface governance.** A code audit of
the recent surfaces found the config editor returns `admin` to **any** bearer
when SSO is off (`PATCH /v1/daari/config` + `persist: true` writes
config.yaml from a scoped virtual key); the web-ui renders API fields via
`innerHTML` with no CSP and persists keys in localStorage; OCR metrics
collapse into the chat modality; `/v1/systemone` drops the new multimodal
`images` field and has no dedicated rate family.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 34 | Master-key gate on `/v1/daari/config` writes when SSO off | 5 | 2 | LiteLLM 1.104 master-key admin routes | Local check; `master_key_matches` already in the SSO-on path | Filed [#1441](https://github.com/naveenreddyalka/daari/issues/1441) |
| 35 | gpt-6.1-sol pricing / capabilities / param compat | 4 | 1 | LiteLLM price map cadence | Cost-true local-vs-frontier escalation is the core pitch | Filed [#1442](https://github.com/naveenreddyalka/daari/issues/1442) |
| 36 | `/v1/systemone` multimodal `images` + dedicated rate family | 4 | 1 | Ollama 0.35.1 native | Decision models stay on-box vs hosted Jev (Kong/Portkey) | Filed [#1443](https://github.com/naveenreddyalka/daari/issues/1443) |
| 37 | Web-ui hardening: escape DOM, CSP, no localStorage keys | 4 | 3 | LiteLLM proxy UI | Static page — escaping + CSP are cheap, no cloud session infra | Filed [#1444](https://github.com/naveenreddyalka/daari/issues/1444) |
| 38 | OCR modality mislabeled as chat in Prometheus; no guardrails/OTel | 4 | 2 | Kong per-modality costs | Local OCR pitch needs honest FinOps + redaction | Filed [#1445](https://github.com/naveenreddyalka/daari/issues/1445) |
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

Shipped since 2026-10-05 scan — do not re-file: web-ui stats cards for
`compact_to_fit_tokens_dropped` + `mcp_grant_denied`; web-ui compact tokens on
traces; `observability.structured_json_logs` ownership + doctor tip;
savings-report compact pin; compare-litellm 1.105 RC note; everything in the
2026-09-30→10-05 waves (compact-to-fit full stack, MCP grant fail-closed full
stack, OBO, refuse-weak-master-key, decision classifier, `/v1/ocr`,
`/v1/systemone`, MCP registry/proxy/OAuth mint, watchdog dedupe + hatch docs).

Watch rows (audit-verified 2026-10-06, file on trigger — see MEMORIES for
evidence): watchdog kickstart has no fatal-config classifier/backoff (source of
the open local-E2E regression trackers; file if they keep spamming); decision
classifier has no Prometheus latency/outcome series (trace step only, up to 5s
silent tax); MCP OAuth mint lacks `audit_log` events + rotation/revoke;
`/mcp/proxy` lacks cost headers + guardrails; `GET /v1/mcp/registry.json` is
auth-open by design (doctor tip exists — revisit on operator ask);
compact_to_fit token estimate ignores `images`/`audio` and image-only turns
are droppable; Anthropic Models API `line` field parity on the native
`/v1/models`; gpt-6.1-sol Responses multi-agent beta; Portkey-style identified
502 for unreachable MCP egress (chat path returns in-band tool failure by
design). Verified fine — don't re-audit: OCR has `ocr` rate family + budgets +
`post_l6`; systemone meters spend/usage + Prom `systemone` modality + cost
headers; MCP OAuth enforces `exp`; compact protects system/tool pairs,
fail-closed, no L0/L1 key pollution; classifier degrades to heuristic +
`tier_override` bypass; web-ui binds 127.0.0.1 by default.

---

## Path to enterprise-grade — next 5 milestones

1. **Admin-plane trust** — master-key gate on config writes when SSO is off
   (row 34) + web-ui escape/CSP/key-handling hardening (row 37). An admin
   surface a tenant key can rewrite is the first thing an enterprise reviewer
   rejects.
2. **Cost truth for the October frontier lineup** — gpt-6.1-sol pricing,
   capabilities, param compat (row 35); 5× cheaper L6 changes escalation
   economics.
3. **Decision-model depth** — systemone images + rate family (row 36) now;
   classifier Prometheus observability from the watch list next.
4. **Modality observability honesty** — OCR mislabel + guardrails + OTel
   (row 38), then OTel spans for the other new modalities.
5. **Live config + governance depth** — hot-reload `config.yaml` (row 6) and
   the parked Messages tool allowlist (row 7) once the loop frees up.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds) stay deferred until buyer demand.

---

## Changelog

- **2026-10-06 (admin-plane + new-surface governance)** — Outward: Kong 2.2.0,
  Portkey v2.27.0, Ollama 0.35.1 multimodal decision models, OpenAI
  gpt-6.1-sol, Anthropic `line`; LiteLLM bar unchanged at 1.104 GA. Inward
  audit of the new surfaces found the SSO-off config editor trusting any
  bearer, web-ui XSS/CSP/key-storage seams, OCR metrics collapsing to chat,
  and systemone dropping Clef images. Filed five issues (rows 34–38). The
  10-05 Actions sibling's PRD PR never merged (its CI tripped the hermetic
  PRD pin by pruning required rows) — its five gaps shipped anyway and are
  folded into the shipped list above.

- **2026-10-05 (operate-gates + FinOps surface shipped)** — Grafana compact,
  grant counter, initialize refuse, token-drop stats, compare-litellm 1.104
  marked Shipped; the FinOps/container-ops refill (web-ui stats,
  structured_json_logs ownership/doctor, savings-report pin, 1.105 note)
  drained same-day.

- **2026-10-04** — LiteLLM **1.104.0 GA**; operate-gate issues filed then
  shipped; compact + MCP grant stacks marked Shipped.

- **2026-10-01 → 09-15 and earlier** — Condensed: OBO + refuse-weak-key +
  classifier + config ownership; decision models + MCP OAuth depth;
  structured outputs; client honesty; MCP ops; local MCP execution;
  2026-07-28 fidelity; gateway-backend completeness; Apache 2.0; this PRD's
  creation (2026-08-28).
