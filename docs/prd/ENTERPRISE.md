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

## Where daari stands (verified in-tree, 2026-10-08)

**Loop velocity.** Rows 44–48 (filed 10-07) all landed on `main` within a day:
`/v1/decisions` + gpt-6-luna pricing (incl. decisions input-only path), MCP OAuth
scope + RFC 7009 revoke, OTel/guardrails/retry on `/mcp/proxy` + `/v1/systemone`,
web-ui keys/teams admin read plane, Responses multi-agent forward-or-400.
Anthropic `thinking.types.disabled` on native `/v1/models` also shipped. Hot-reload
`config.yaml` stays in flight; Messages `mcp_servers` tool allowlist stays parked.

**Outward.** OpenAI Decisions beta (`gpt-6-luna`, 6 Oct) and gpt-6.1-sol
multi-agent beta remain the active client APIs to deepen. LiteLLM bar still
**v1.104.0 GA** (1.105/1.106 RCs: M365 MCP catalog + scoped-SQL — watch for GA).
Portkey / Kong / OpenRouter flat vs prior scan.

**Inward theme: depth on surfaces that just shipped.** Code audit (10-08)
confirmed: `/v1/decisions` meters Prom `decisions` modality but skips
guardrails/OTel and the local path bypasses systemone hardening; MCP revoke
denylist is process-local (no fleet/backup); admin keys/teams dumps are
unpaginated and unaudited; multi_agent L6 only reads top-level usage; doctor /
Helm / auth-and-keys lag the new Decisions family.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 49 | Guardrails + OTel (+ local retry) + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong policy on decisions `state`; OCR parity in-tree | Same on-box policy engine as systemone/OCR | Filed [#1497](https://github.com/naveenreddyalka/daari/issues/1497) |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist (Redis/Postgres) | 5 | 3 | Kong Token Vault; LiteLLM shared revoke stores | Revoke must stick across Helm replicas | Filed [#1498](https://github.com/naveenreddyalka/daari/issues/1498) |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM proxy admin UI audit trail | Control-plane honesty at key-store scale | Filed [#1499](https://github.com/naveenreddyalka/daari/issues/1499) |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage; LiteLLM agent cost split | FinOps chargeback for delegated agents | Filed [#1500](https://github.com/naveenreddyalka/daari/issues/1500) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface before rate-family miss | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta | Typed judgments on-box | Shipped |
| 45 | MCP OAuth scope + RFC 7009 revocation | 4 | 2 | LiteLLM / Kong | On-box revoke/scope | Shipped |
| 46 | OTel + guardrails + retry on `/mcp/proxy` + `/v1/systemone` | 4 | 2 | Kong / Portkey | Local policy latency | Shipped |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM admin UI | Same-box console | Shipped |
| 48 | Responses multi-agent forward or honest 400 | 3 | 2 | OpenAI multi-agent beta | Transparent L6 delegation | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): `/v1/decisions` + luna pricing; MCP OAuth
scope/revoke endpoint; systemone/mcp_proxy/OCR hardening stacks; admin read
plane existence; multi-agent forward; Anthropic `thinking.types.disabled`;
web-ui CSP/sessionStorage; classifier Prom series. Open watch (do not file
yet): Decisions L0/exact cache; Decisions stream/batch/Ollama-Anthropic
facades; admin dedicated rate family; gpt-6-luna schema drift; LiteLLM
1.105/1.106 GA catalog; age-encrypt backup restore test.

Verified fine this run — don't re-audit: Prom `decisions` modality +
`rate_families` mapping; luna in `_DEFAULT_MODEL_PRICES` with decisions
billing_path; revoke `_prune_revoked` TTL cleanup; web-ui Bearer in memory /
opt-in `sessionStorage` (no localStorage); `/v1/decisions` listed in
http-api.md; batches still chat-only by design (`_execute_batch_chat_body`).

---

## Path to enterprise-grade — next 5 milestones

1. **Decisions governance parity** — guardrails + OTel + local retry + `user`
   spend on `/v1/decisions` (row 49), matching systemone/OCR.
2. **MCP revoke that survives replicas** — durable jti denylist (row 50) so
   Helm `replicaCount>1` is safe.
3. **Admin read plane at scale** — pagination + audit events (row 51).
4. **Multi-agent FinOps** — honest subagent token/spend metering (row 52).
5. **Ops discoverability** — doctor/Helm/auth-and-keys for Decisions (row 53),
   then hot-reload (row 6) and the parked Messages tool allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-08 (depth on shipped Decisions / OAuth / admin / multi-agent)** —
  Rows 44–48 marked Shipped. Inward audit filed rows 49–53: decisions
  guardrails/OTel, fleet OAuth denylist, admin pagination/audit, multi_agent
  spend metering, decisions ops docs. Pricing table still has `gpt-6-luna`;
  no additional missing frontier id vs in-tree recent catalog adds.

- **2026-10-07 (decisions surface + lifecycle depth)** — Filed rows 44–48
  (local-first `/v1/decisions`, MCP OAuth scope/revocation, new-surface
  spans/guardrails/retry, web-ui admin read plane, Responses multi-agent).

- **2026-10-06 → 08-28** — Condensed: catalog + classifier/watchdog; admin-plane
  + OCR governance; operate-gates + FinOps; LiteLLM 1.104; OBO/classifier;
  decision models + MCP OAuth; Apache 2.0; this PRD's creation.
