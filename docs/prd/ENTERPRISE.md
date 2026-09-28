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

## Where daari stands (verified in-tree, 2026-09-28 evening)

**Loop velocity.** Morning’s MCP server allowlists + tools/call metering already
merged; resilience / refreshable secrets / Helm header_policy still in flight.
P3 docs hermetic pins remain. Backlog had room for the next protocol and
ops slice.

**Outward.** LiteLLM docs: **v1.102.0** stable (strict MCP grants, `/mcp/proxy`
schema discovery, OCR default, OTel HTTP/JSON); **v1.103.0-rc.1** (config-file
ownership, MCP client allowlisting, live session force-close, RFC 8693). Portkey
enterprise changelog leads with **v2.20.0** Unified Gateway + MCP Server Mode
and continuing MCP SSRF/TLS fetch hardening. Kong AI Gateway **2.1+** maps
`server/discover` for MCP **2026-07-28** (sessionless). vLLM **0.30.0**; Ollama
**0.34.4** stable / **0.40.0-rc0** (MLX default on Apple Silicon). OpenRouter /
MCP SEP-1933 still quiet.

**Inward theme: 2026-07-28 fidelity + egress trust + FinOps usability.** Code
audit: daari *lists* `2026-07-28` but only bootstraps via `initialize` — no
`server/discover`, no per-request `_meta` protocolVersion. MCP egress POSTs to
any configured URL with no private/metadata SSRF guard (Portkey already
external-fetch-hardens this). Server grants shipped; *client* identity grants
did not. Encrypted backup CLI exists; Helm has no CronJob scheduler. MCP
metering landed, but `daari spend report` still only `--by-user`.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **MCP `server/discover` + per-request `_meta` version** — advertises 2026-07-28 but initialize-only | 5 | 2 | Kong 2.1+ / MCP spec MUST | Sessionless local peer; no sticky store | Filed — P1 ([#1213](https://github.com/naveenreddyalka/daari/issues/1213)) |
| 2 | **MCP egress SSRF / private-network guards** — any URL POSTed | 5 | 2 | Portkey external-fetch SSRF/TLS path | Config-declared servers + local deny-by-default | Filed — P1 ([#1214](https://github.com/naveenreddyalka/daari/issues/1214)) |
| 3 | **Per-key/team MCP client allowlists** — server/tool grants without client identity gate | 4 | 2 | LiteLLM 1.103-rc (client allowlisting) | Same VK-metadata policy, offline audit | Filed — P2 ([#1215](https://github.com/naveenreddyalka/daari/issues/1215)) |
| 4 | **Scheduled encrypted backups** — encrypt+restore shipped; scheduling manual | 3 | 2 | pgBackRest / cloud DR schedulers | Reuse `daari backup --encrypt` from CronJob/timer | Filed — P2 ([#1216](https://github.com/naveenreddyalka/daari/issues/1216)) |
| 5 | **`daari spend report --by-tool`** — MCP metering landed; CLI rollup missing | 3 | 1 | Kong per-RPC MCP analytics | Local ledger → chargeback, no SaaS | Filed — P2 ([#1217](https://github.com/naveenreddyalka/daari/issues/1217)) |
| 6 | MCP egress resilience (OTel span, retry, per-server breaker) | 4 | 2 | Kong / Portkey | In flight from morning cycle | Open — morning backlog |
| 7 | Refreshable `secret://` resolution | 4 | 2 | Cloud control planes | In flight | Open — morning backlog |
| 8 | Helm header_policy knobs + `/mcp` deny pin | 3 | 1 | Portkey startHooks | In flight | Open — morning backlog |
| 9 | MCP ingress activity visibility + force-close | 4 | 3 | LiteLLM 1.103-rc | Frame as connection/activity ops, not spec sessions | Watch |
| 10 | MCP inbound OAuth / RFC 9728; full-config SIGHUP; native `/v1/ocr`; Anthropic `output_config.effort`; A2A; admin UI | 2–5 | 3–5 | LiteLLM / Portkey / Anthropic | Demand-triggered | Watch |

Shipped since morning audit — do not re-file: per-key/team MCP **server**
allowlists; MCP tools/call spend/usage metering + `mcp` rate family. Still
verified fine: tool allow/deny + audit, semantic tool search, tools/list
ttlMs/cacheScope, tools/list pagination, MCP guardrails, W3C egress trace
injection, oauth `secret://` re-mint, encrypt↔decrypt restore + `--restore-pg`,
header_policy on `/mcp`, config ownership metadata for PATCH safe subset,
lifetime + weekly/rpw budgets.

---

## Path to enterprise-grade — next 5 milestones

1. **2026-07-28 protocol honesty** — `server/discover` + per-request `_meta`
   (row 1) so modern MCP clients treat daari as a correct peer.
2. **Egress trust boundary** — SSRF/private-network guards (row 2), then finish
   resilience spans/retry/breaker (row 6).
3. **Client identity governance** — MCP client allowlists (row 3) on top of
   server/tool grants.
4. **Operator DR + FinOps completeness** — scheduled backups (row 4) and
   `--by-tool` spend (row 5).
5. **Then identity depth on demand** — inbound OAuth / activity visibility
   (rows 9–10) when SEP-1933 lands or fleets ask.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-28 evening (2026-07-28 fidelity + egress trust + FinOps)** —
  Morning server-allowlist + metering merged. Outward: LiteLLM 1.102.0 stable /
  1.103.0-rc.1; Portkey v2.20.0 Unified+MCP; Kong discover mapping; Ollama
  0.40.0-rc0 MLX watch. Filed discover+`_meta` (P1), MCP egress SSRF (P1),
  MCP client allowlists, scheduled backups, spend `--by-tool` (P2s). Sessions /
  inbound OAuth / OCR / Anthropic beta held as watch.

- **2026-09-28 (MCP gateway enterprise depth)** — LiteLLM MCP bar moved;
  filed MCP server allowlists (P1), metering + rate family, egress resilience,
  refreshable secrets, Helm header_policy (P2s). Server allowlists + metering
  merged same day.

- **2026-09-27 (two runs: fleet-backend completeness + governance consistency;
  session OTel + DR depth + Helm parity)** — Filed ten across compact
  governance, erasure completeness, backup honesty/encryption/pg_dump, spend
  user_id, param compat, OTel conversation id, Helm knobs, hermetic benches.
  All merged by 09-28.

- **2026-09-26 (two runs: agent-surface fidelity; Responses honesty +
  retention + operator visibility)** — Filed ten across astra compat, erasure,
  backup, chargeback, reasoning replay, hosted-tool 400s, prune_all,
  prompt-cache fields, drift hash, streaming resume. All merged by 09-27.

- **2026-09-25 (three runs)** — Fifteen issues across images / identity /
  FinOps; all merged by 2026-09-26 14:08.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
