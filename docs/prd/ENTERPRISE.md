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

## Where daari stands (verified in-tree, 2026-09-25 late)

**Outward movers today (late).** **LiteLLM v1.103.0-rc.1** (hours-old): config-file
ownership (`source`/`editable`, refuse runtime writes to file-owned keys),
budgets re-checked on every fallback hop, team-level `model_max_budget` with
key overrides, per-member org spend. Stable bar stays **v1.102.0/v1.102.1**
(stream post-call guardrails, percentile TTFT routing, native OCR). **Portkey
enterprise changelog** still leads on startHooks / JWT workspace membership /
`/v1/decisions`; WIF + MCP gateway guardrails remain watch. **Kong AI Gateway
2.0 GA** (2026-09-01) — MCP bundling, modality-aware cost; 2.1.0 token series
unchanged. Ollama tip remains MLX-default on capable Apple Silicon (stable
since 0.30; 0.40-rc watch).

**Inward theme: FinOps depth + operator honesty** after the evening identity/
shutdown/token-metrics filing. Code audit: `model_groups` are allowlists only
(no shared USD window); doctor probes images/ASR/TTS but not moderations/rerank;
`GET/PATCH /v1/daari/config` mutates live settings without `source`/`editable`
or live-vs-file delta; no pre-auth header screen before `require_api_key`;
teams lack per-model USD caps.

Open from earlier today (not re-filed): SSO governance hole, app-level drain,
cached-token + per-modality metrics, request-time team membership, endpoint
RPM/TPM, images variations, Anthropic moderations ingress, edits integration
pins.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **SSO bearers ungoverned on inference** (evening) | 5 | 2 | (nobody — daari defect) | Governance-by-default | Open — evening filing |
| 2 | **Shared USD budget per `model_group`** — allowlists only today (`settings.model_groups`) | 4 | 3 | LiteLLM v1.100 access-group budgets | On-box FinOps for named catalog slices without SaaS | Filed — see #1109 |
| 3 | **Team `model_max_budget` + key overrides** | 4 | 2 | LiteLLM v1.103-rc.1 | Reserve frontier headroom per model; rest stays local | Filed — see #1113 |
| 4 | **Config live-vs-file ownership honesty** — GET lacks `source`/`editable`; PATCH without persist silently diverges | 4 | 2 | LiteLLM v1.103-rc.1 | `config.yaml` remains operator source of truth | Filed — see #1111 |
| 5 | **App-level graceful shutdown** (evening) | 4 | 2 | Kong / LiteLLM | Zero-drop rollouts as a binary property | Open — evening filing |
| 6 | **Cached-token + per-modality Prometheus/OTel** (evening) | 4 | 2 | Kong 2.1.0 | Local Grafana chargeback | Open — evening filing |
| 7 | **Request-time team membership** (evening) | 4 | 3 | Portkey v2.25 | Multi-team chargeback without key sprawl | Open — evening filing |
| 8 | **Doctor probes for moderations + rerank** | 3 | 1 | (onboarding gap) | Same doctor contract as images/ASR/TTS | Filed — see #1110 |
| 9 | **Pre-auth header allow/block policy** (Portkey startHooks) | 3 | 2 | Portkey v2.25 | Screen scrapers before auth/store work | Filed — see #1112 |
| 10 | Endpoint RPM/TPM; images variations; Anthropic moderations; edits pins (morning) | 3–4 | 2–3 | Portkey / LiteLLM | Route-family parity | Open — morning filing |
| 11 | Watch: `/v1/decisions`, `/v1/ocr`, WIF, A2A, MCP live sessions, SOC 2, admin UI, Realtime/WS, budget-on-fallback recheck | 2–4 | 2–5 | LiteLLM / Portkey / cloud | Demand-triggered | Watch |

Pruned this run: none newly shipped since evening; kept evening identity rows
as open pointers without re-filing. Do not re-file closed images-edits work.

---

## Path to enterprise-grade — next 5 milestones

1. **Close the SSO governance hole** — every authenticated identity class is
   budget-fenced and attributed (evening P1).
2. **FinOps depth** — model-group shared budgets + team `model_max_budget`,
   then cached-token / per-modality metrics from the evening set.
3. **Operator honesty** — live-vs-file config ownership + doctor probes for
   every shipped modality + app-level drain.
4. **Request-time team resolution** — membership-enforced team selection
   (evening) plus pre-auth header policy for tunnel-exposed endpoints.
5. **Drain morning modality backlog** — endpoint RPM/TPM, images variations,
   Anthropic moderations ingress.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, Realtime) stay deferred.

---

## Changelog

- **2026-09-25 late (FinOps depth + operator honesty)** — Third scan of the
  day. Outward: LiteLLM v1.103.0-rc.1 (config ownership, model_max_budget,
  fallback budget recheck); stable bar still v1.102.x; Portkey/Kong/Ollama
  unchanged vs evening. Inward: filed five — model_group shared USD budgets,
  team model_max_budget + key overrides, config live-vs-file ownership,
  doctor moderations/rerank probes, pre-auth header allow/block (startHooks
  parity). Watch: OCR, decisions API, budget-on-fallback recheck. Evening
  identity/shutdown/token rows remain open.

- **2026-09-25 evening (identity edges + shutdown + token observability)** —
  Portkey v2.25.0, Ollama v0.40.0-rc0 watch, LiteLLM backport wave. Filed
  SSO ungoverned bearers (P1), graceful shutdown, cached-token observability,
  per-modality token metrics, request-time team membership.

- **2026-09-25 morning (images L6 surface closed → next layer)** — Images
  edits/variations, creative metering, endpoint-scoped RPM, Anthropic
  moderations; edits + cost-header pins shipped same day.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
