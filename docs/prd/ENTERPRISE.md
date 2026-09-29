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

## Where daari stands (verified in-tree, 2026-09-29)

**Loop velocity.** Overnight P1s (`server/discover` + `_meta`, MCP egress SSRF)
and morning P2s (egress resilience, refreshable `secret://`, Helm
`header_policy`) all merged. Evening P2s still open: MCP client allowlists,
scheduled encrypted backups, spend `--by-tool`. P3 docs hermetic pins remain.

**Outward.** LiteLLM **v1.103.0-rc.1** (hours-old): MCP client allowlisting,
live session visibility + admin force-close, RFC 8693 token exchange, Fuse
routing, OCR Rust path hardening; **v1.102.0** stable still the OCR-default /
`/mcp/proxy` schema-discovery bar. Portkey **v2.20.0** Unified Gateway + MCP
Server Mode and **server-side MCP** beta for Responses/Messages. Kong AI
Gateway **2.1+** 2026-07-28: `server/discover`, per-request version, and
`Mcp-Method`/`Mcp-Name` body match. Anthropic ships stable
`output_config.effort` (LiteLLM already maps it). Ollama **0.34.4** stable /
**0.40.0-rc0** + **0.35.0** pre; vLLM **0.30.0**.

**Inward theme: client-contract honesty + MCP ops + local MCP execution.**
Claude Code effort knobs are dropped today (`AnthropicRequest` has no
`output_config`). MCP headers are read for governance but not mismatch-
rejected. No admin view/abort of in-flight MCP calls (LiteLLM just shipped
that). Responses still 400s `type:mcp` tools; Portkey executes them in-gateway.
Safe config PATCH exists; full `config.yaml` still needs restart.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Anthropic `output_config.effort`** — dropped on Messages; Claude Code slider ignored | 5 | 2 | LiteLLM effort mapping | Local think map + honest L6 passthrough | Filed — P1 ([#1230](https://github.com/naveenreddyalka/daari/issues/1230)) |
| 2 | **MCP ingress activity + admin force-abort** — no list/kill for in-flight tools/call | 4 | 3 | LiteLLM 1.103 live sessions | Request-scoped registry; no sticky sessions | Filed — P2 ([#1231](https://github.com/naveenreddyalka/daari/issues/1231)) |
| 3 | **Server-side MCP in Responses** — `type:mcp` still 400; Portkey executes in-gateway | 5 | 3 | Portkey v2.20 server-side MCP | Reuse local egress + SSRF + metering | Filed — P2 ([#1232](https://github.com/naveenreddyalka/daari/issues/1232)) |
| 4 | **`Mcp-Method` / `Mcp-Name` body match** — headers read, mismatches allowed | 3 | 1 | Kong 2.1+ 2026-07-28 | Fail-closed sessionless peer | Filed — P2 ([#1233](https://github.com/naveenreddyalka/daari/issues/1233)) |
| 5 | **Hot-reload `config.yaml`** — PATCH safe subset only; full file needs restart | 3 | 2 | LiteLLM / cloud CPs | `POST /v1/daari/reload-config` (+ optional SIGHUP) | Filed — P2 ([#1234](https://github.com/naveenreddyalka/daari/issues/1234)) |
| 6 | Per-key/team MCP client allowlists | 4 | 2 | LiteLLM 1.103-rc | Open — prior cycle | Open |
| 7 | Scheduled encrypted backups (Helm CronJob / timer) | 3 | 2 | pgBackRest-class schedulers | Open — prior cycle | Open |
| 8 | `daari spend report --by-tool` | 3 | 1 | Kong per-RPC analytics | Open — prior cycle | Open |
| 9 | MCP inbound OAuth / RFC 9728; native `/v1/ocr`; `/mcp/proxy` schema discovery; A2A; admin UI | 2–5 | 3–5 | LiteLLM / Portkey / Anthropic | Demand-triggered | Watch |

Shipped since prior evening audit — do not re-file: `server/discover` + per-request
`_meta`; MCP egress SSRF/private-network guards; MCP egress OTel/retry/breaker;
refreshable `secret://`; Helm `header_policy` + `/mcp` deny pin. Still verified
fine: MCP server allowlists; tools/call metering + `mcp` rate family; tool
allow/deny + audit; semantic tool search; tools/list ttlMs/cacheScope +
pagination; MCP guardrails; W3C egress trace injection; oauth `secret://`
re-mint; encrypt↔decrypt restore + `--restore-pg`; config ownership metadata;
lifetime + weekly/rpw budgets.

---

## Path to enterprise-grade — next 5 milestones

1. **Client-contract honesty** — Anthropic `output_config.effort` (row 1) so
   Claude Code cost knobs survive the local gateway.
2. **MCP ops kill-switch** — in-flight activity + force-abort (row 2) matching
   LiteLLM’s live-session admin bar without inventing sticky sessions.
3. **Local MCP execution for agents** — server-side Responses MCP (row 3) so
   Bedrock/Vertex/Ollama paths keep tool creds on-box.
4. **2026-07-28 header honesty** — Method/Name mismatch reject (row 4), then
   finish prior-cycle client allowlists / DR / FinOps (rows 6–8).
5. **Operator live config** — hot-reload (row 5); then inbound OAuth / OCR /
   schema-proxy (row 9) on buyer demand.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-29 (client honesty + MCP ops + local MCP execution)** — Overnight
  discover/SSRF and morning resilience/secrets/Helm merged. Outward: LiteLLM
  1.103.0-rc.1 force-close + client allowlists; Portkey server-side MCP beta;
  Kong Method/Name match; Anthropic `output_config.effort`. Filed effort
  passthrough (P1), MCP activity/abort, Responses server-side MCP, header
  mismatch reject, config hot-reload (P2s). Prior-cycle client allowlists /
  backups / `--by-tool` remain open. OAuth / OCR / A2A held as watch.

- **2026-09-28 evening (2026-07-28 fidelity + egress trust + FinOps)** —
  Filed discover+`_meta`, MCP egress SSRF (P1s), MCP client allowlists,
  scheduled backups, spend `--by-tool` (P2s). Discover + SSRF merged 09-29.

- **2026-09-28 (MCP gateway enterprise depth)** — Filed MCP server allowlists
  (P1), metering + rate family, egress resilience, refreshable secrets, Helm
  header_policy (P2s). All merged by 09-29.

- **2026-09-27 → 09-15 and earlier** — Condensed: fleet-backend completeness,
  governance, agent-surface fidelity, Responses honesty, images/identity/
  FinOps, non-chat endpoint parity, Apache 2.0, this PRD's creation (2026-08-28).
