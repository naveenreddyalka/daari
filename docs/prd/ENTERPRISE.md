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

## Where daari stands (verified in-tree, 2026-09-28)

**Loop velocity.** The entire 09-27 table (both runs, ten rows) drained in under
24 hours: compact/Responses governance, fleet erasure, backup catalog honesty +
encryption + embedded `pg_dump`, spend `user_id` on modalities, config-driven
param compat, OTel `gen_ai.conversation.id`, Helm sessionAffinity/policySync,
hermetic compact/resume benches, plus a new `server.header_policy` pre-auth
middleware with operator guide. Backlog at scan time: two sibling P3 docs/test
rows only.

**Outward.** **LiteLLM v1.103.0 went STABLE 2026-09-28** (bar moves from
v1.102.1): MCP client allowlisting with per-key/team MCP *server* grants, live
MCP session visibility + force-close, RFC 8693 token exchange, per-issuer JWT
scoping, lifetime budgets, config-file ownership; v1.104.0-rc.1 cut the same
day. Portkey enterprise changelog still tops **v2.25.0**; Kong AI Gateway
**2.1.0** (MCP 2026-07-28 revision — which mints **no sessions** — plus per-RPC
MCP analytics and trace propagation); vLLM **0.30.0**; Ollama **0.34.4** stable
/ **0.40.0-rc0** (MLX) watch; OpenRouter changelog last 08-19; MCP blog last
08-22 (SEP-1933 agent identity still draft).

**Inward theme: MCP gateway enterprise depth.** Code audit of
`daari/gateway/mcp*.py` + `daari/providers/mcp_egress.py`: tool-name governance
(#277), semantic tool search, ttlMs/cacheScope hints, and 2026-07-28 protocol
support are all in-tree — but there is no *server-level* egress allowlist per
key/team, provider-backed `tools/call` writes zero spend/usage rows (`/mcp`
rate family is `other`), egress has no retry/breaker/OTel span (single POST,
fail-open once), non-oauth `secret://` refs resolve once at boot (rotation
requires restart), and the new header_policy has no Helm knobs and no `/mcp`
deny-path pin.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Per-key/team MCP server allowlists** — tool-name globs cannot express server tenancy | 5 | 2 | LiteLLM v1.103.0 stable (per-key MCP grants) | Same VK-metadata policy engine, fully offline + audited | Filed — P1 ([#1201](https://github.com/naveenreddyalka/daari/issues/1201)) |
| 2 | **MCP tools/call spend/usage metering + `mcp` rate family** — provider tools invisible to chargeback; `/mcp` rate family is `other` | 4 | 2 | Kong 2.1.0 per-RPC MCP analytics | Highest-risk surface joins the existing local ledgers/export/erasure | Filed — P2 ([#1202](https://github.com/naveenreddyalka/daari/issues/1202)) |
| 3 | **MCP egress resilience** — no OTel client span, retry, or per-server breaker | 4 | 2 | Kong (trace + analytics), Portkey (OAuth robustness) | Reuse in-tree RetryPolicy/CircuitBreaker/OTel; one resilience model for LLM + tool upstreams | Filed — P2 ([#1203](https://github.com/naveenreddyalka/daari/issues/1203)) |
| 4 | **Refreshable `secret://` resolution** — non-oauth refs boot-cached; rotation forces rolling restart | 4 | 2 | Cloud control planes push creds live | `secret://exec` composes with any vault CLI, no cloud secret manager | Filed — P2 ([#1204](https://github.com/naveenreddyalka/daari/issues/1204)) |
| 5 | **Helm header_policy knobs + `/mcp` deny pin** — new middleware env-only; chat-only test pin | 3 | 1 | Portkey startHooks (cloud config plane) | Pre-auth header screening from a values file | Filed — P2 ([#1205](https://github.com/naveenreddyalka/daari/issues/1205)) |
| 6 | MCP ingress session/activity visibility + force-close | 4 | 3 | LiteLLM v1.103.0 stable | 2026-07-28 revision mints **no sessions** — frame as connection/activity observability, not spec sessions | Watch — file on fleet demand from pre-2026-07-28 clients |
| 7 | MCP inbound OAuth / RFC 9728 protected-resource metadata | 5 | 4 | LiteLLM (RFC 8693, per-issuer JWT) | Local IdP integration via existing SSO/JWKS plumbing | Watch — SEP-1933 still draft; file when it merges or a fleet asks |
| 8 | Full-config hot reload / SIGHUP (PATCH covers safe subset only) | 4 | 3 | Kong/Portkey live policy reload | `daari migrate` + policy_sync exist; secret refresh (row 4) covers sharpest slice | Watch — operator demand |
| 9 | Scheduled backups (Helm CronJob / timer unit) — encrypt+restore shipped, scheduling manual | 3 | 2 | pgBackRest et al. | One-command encrypted DR already in-tree | Watch — file on DR-audit ask |
| 10 | Anthropic beta fidelity (`output_config.effort`, `tool_addition`); native `/v1/ocr`; org-above-teams; decisions API; A2A; admin UI | 2–4 | 3–5 | Anthropic / LiteLLM / Portkey | Demand-triggered | Watch |

Verified fine this audit — do not re-file: MCP tool allow/deny per key/team +
audit (`mcp_policy.py`), semantic tool search wired into egress, tools/list
ttlMs/cacheScope hints, protocol 2026-07-28 negotiation, W3C trace injection on
egress, `daari migrate` + doctor pending-migrate check, PATCH safe-config
subset, oauth `secret://` re-mint at use, openssl encrypt↔decrypt restore
round-trip + `--restore-pg`, compact responses resumable via stored-body SSE
synthesis, `daari spend report --by-user`, header_policy covers `/mcp`
(open-path set is health/ready/metrics only), no WebSocket surface to govern.

---

## Path to enterprise-grade — next 5 milestones

1. **MCP governance parity** — server-level grants per key/team (row 1) and
   full chargeback on tool calls (row 2): the agent-tool surface governs,
   meters, and audits exactly like chat.
2. **MCP data-plane resilience** — spans, retries, breakers on egress (row 3)
   so external tool servers get the same SLO story as LLM upstreams.
3. **Zero-restart operations** — refreshable secrets (row 4), then full config
   reload (row 8) as demand confirms.
4. **Install-review completeness** — every shipped control reachable from Helm
   values (row 5 closes the header_policy gap opened this week).
5. **Then identity depth on demand** — MCP inbound OAuth (row 7) and
   session/activity visibility (row 6) when SEP-1933 lands or fleets ask.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-28 (MCP gateway enterprise depth)** — LiteLLM v1.103.0 stable
  (MCP allowlisting, live sessions, RFC 8693) moved the bar; everything else
  outward flat. Whole 09-27 table drained overnight. Filed MCP server
  allowlists (P1), MCP metering + rate family, MCP egress resilience,
  refreshable secrets, Helm header_policy knobs (P2s). Sessions + inbound
  OAuth held as watch rows (2026-07-28 revision is sessionless; SEP-1933
  draft).

- **2026-09-27 (two runs: fleet-backend completeness + governance consistency;
  session OTel + DR depth + Helm parity)** — Filed ten across compact
  governance, erasure completeness, backup honesty/encryption/pg_dump, spend
  user_id, param compat, OTel conversation id, Helm knobs, hermetic benches.
  All merged by 09-28.

- **2026-09-26 (two runs: agent-surface fidelity; Responses honesty +
  retention + fleet visibility)** — Filed ten across astra compat, erasure,
  backup, chargeback, reasoning replay, hosted-tool 400s, prune_all,
  prompt-cache fields, drift hash, streaming resume. All merged by 09-27.

- **2026-09-25 (three runs)** — Fifteen issues across images / identity /
  FinOps; all merged by 2026-09-26 14:08.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
