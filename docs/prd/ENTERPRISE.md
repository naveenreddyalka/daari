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

## Where daari stands (verified in-tree, 2026-09-25)

**Outward: still flat.** **Ollama v0.34.4** unchanged — structured outputs on
thinking models remain internal. **LiteLLM** stable bar **v1.102.1**; tip
**v1.104.0-dev.1** (MCP live sessions, Transcribe passthrough, vault namespaces —
file MCP sessions when the tip stabilizes). **Portkey** open-source gateway tag
still **v1.15.2** (weekly/rpw windows, endpoint-scoped limits, Agent Gateway on
the product side). **Kong AI Gateway 2.0** GA wave + **vLLM 0.30.0** unchanged.
No new OpenRouter API surface.

**Inward theme: creative-surface hardening + operator honesty.** Yesterday's
modality/client-contract layer is **closed on main**: governed
`POST /v1/images/generations` (governance, Idempotency-Key, guardrails, cost
headers, integration pins), Idempotency-Key on embeddings/audio/moderations/
rerank, facade forward-or-declare for Ollama 0.34 `tool_search` /
`response_compaction`, `week`/`weekly`/`rpw` budget aliases, moderations/rerank
gateway-flow pins, and a doctor dry-probe for images when frontier is on.

Verified shipped — pruned from watch: images/generations L6 slice + follow-ons,
modality Idempotency-Key, facade 0.34 honesty, FinOps week/rpw aliases,
moderations/rerank integration pins, morning non-chat governance set
(allowlists/`no_frontier`/ledger, guardrails on payloads, ASR claim fence,
modality cost headers, retry/`region_pin`), doctor images probe.

**Next layer:** finish the OpenAI images family (edits/variations), deepen
metering/test bar on creative routes, and pick operator gaps competitors
already sell (endpoint-scoped RPM, MCP session visibility, Anthropic-native
moderation ingress).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **No `POST /v1/images/edits` (and variations)** — generations is on-box; edit/variation clients still need a second base URL | 4 | 2 | LiteLLM / Portkey | Same L6 key fence + governance for the rest of the OpenAI images family | File next |
| 2 | **Images cost-header coverage thin outside route tests** — shared `test_cost_headers` suite does not pin the creative path | 3 | 1 | (internal bar) | One metering contract across modalities; prevents silent header drift | File next |
| 3 | **No endpoint-scoped RPM/TPM families** — Portkey sells per-route quotas; daari is mostly global / key-scoped | 4 | 3 | Portkey | Local fleets need chat vs embed vs images budgets without a second gateway | File next |
| 4 | **MCP live-session visibility missing** — LiteLLM tip tracks live MCP sessions; daari probes are request-scoped only | 3 | 3 | LiteLLM tip | Operators debugging local agent loops need session liveness without cloud | Watch (file on tip stable) |
| 5 | **No Anthropic-native moderations ingress** — OpenAI `/v1/moderations` exists; Anthropic clients still dual-home | 3 | 2 | cloud gateways | One local root for mixed OpenAI + Anthropic moderation traffic | File next |
| 6 | Watch queue: WIF upstream creds, A2A, SOC 2, admin UI, OpenAI Realtime/WebSocket surface, vault-style secret namespaces | 2–4 | 2–5 | LiteLLM / Portkey / cloud | Operator or client demand triggers these | Watch |

Pruned this run: five 09-24 evening modality/client-contract filings (all
shipped), plus doctor images probe. Do not re-file closed work.

---

## Path to enterprise-grade — next 5 milestones

1. **Complete the OpenAI images family** — governed edits/variations beside
   generations so creative SDKs share one local root.
2. **Metering and test bar for creative routes** — shared cost-header pins and
   chargeback honesty for image spend.
3. **Endpoint-scoped rate families** — Portkey-parity chat/embed/images quotas
   on virtual keys without leaving the box.
4. **MCP session operator plane** — live-session visibility when the LiteLLM
   tip shape stabilizes (or invent a local-first equivalent sooner).
5. **Anthropic moderation ingress** — stop dual-homing mixed-stack clients.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

- **2026-09-25 (images L6 surface closed → next layer)** — Overnight drain
  closed the 09-24 evening modality/client-contract set plus images follow-ons
  (Idempotency, guardrails, cost headers, integration pins) and doctor images
  probe. Outward still flat (Ollama v0.34.4; LiteLLM bar v1.102.1 / tip
  v1.104.0-dev.1 MCP sessions watch; Portkey/Kong/vLLM unchanged). Next:
  images edits/variations, creative metering test bar, endpoint-scoped RPM,
  Anthropic moderations ingress; MCP sessions remain watch. Pruned five shipped
  evening rows + doctor probe.

- **2026-09-24 evening (modality surface + client-contract honesty)** —
  Outward still flat. Filed images/generations, modality Idempotency-Key,
  facade 0.34 honesty, week/rpw aliases, moderations/rerank integration pins.
  All drained by 09-25.

- **2026-09-24 (non-chat endpoint parity)** — Filed non-chat governance/
  metering/guardrails/ASR fence/cost headers. Drained same day into evening
  scan.

- **2026-09-23 (two runs: client parameter fidelity; facade + Responses
  shapes)** — Silent drops across ingresses, then facade/Responses/MCP probe/
  stream failover. Filed ten; drained by 09-24.

- **2026-09-22 (two runs)** — Data-plane efficiency + stream truncation
  fidelity, then correlation + modality resilience. Portkey v2.24.0, Kong
  2.1.0, vLLM 0.30.0.

- **2026-09-21 (two runs)** — Data-plane hardening + lossless escalation, then
  browser/ops + agent SDK knobs.

- **2026-09-15 → 09-20 and earlier** — Condensed: governance secondary
  ingress + resilience/modality delta; embed/ASR measurement + cache tenancy
  + request lifecycle; soft-budget drain + governance/chargeback theme; loop
  restructure (never-empty refill + scheduled Actions prd run); fleet-auth,
  fleet story, resilience + metering, stored-artifact tenancy, Batch/Files
  API, pricing refresh, session affinity, stall escalation, MCP pagination,
  Apache 2.0 relicense, this PRD's creation (2026-08-28).
