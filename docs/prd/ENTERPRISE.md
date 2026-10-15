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

## Where daari stands (verified in-tree, 2026-10-15)

**Loop velocity.** Both 10-14 tables drained in under a day again: rows 97–101
(PG request-log erasure, fail-closed PG auth/budgets, model lifecycle +
`shutdown_date`, MCP 429 audit/Prom, migrate/doctor PG schemas) shipped as
PRs #1663–#1667, and the eve sibling's rows 102–106 (cache-invalidate audit,
Anthropic `decision` capability, mcp_servers ceilings in config/Helm,
cache-invalidate Grafana/alerts, error status labels) as PRs #1668–#1672.
The dead eve PRD PR was drained to main. Open: member webhooks (90), DEC/SYS
bench docs (91), compare rows (96/78), and `agent:working` rows 62–63/65–67.

**Outward.** **Anthropic launched OpenTelemetry export in beta (10-14)**:
Messages API tracing plus SDKs that register spans with the global tracer
and inject trace-context headers — Anthropic SDK clients pointed at daari's
`/v1/messages` now arrive traced (daari's inbound `traceparent` extraction
already parents them; a W3C `traceresponse` reply header is the missing
half). **Portkey v2.29.0**: JWT claims extracted into request metadata for
conditional routing, `/v1/decisions` auto-detects OpenAI-native vs Jev
schemas, MCP gateway honors client `traceparent`. LiteLLM stable holds at
1.105.1; 1.107-dev adds `traceresponse`, a caller-IP logging opt-out, Helm
DB/Redis from k8s Secrets, deployment-warning endpoints. Kong 2.2.0, vLLM
0.31.0, Ollama 0.40.4, OpenRouter (Oct 9), MCP blog (Aug 22) flat.

**Inward theme: depth behind the shipped wave.** Code audit verified: the
retired-model 410 gate covers chat/messages/responses but **not** the Ollama
facade, decisions, embeddings, OCR, or systemone — ChatGPT Desktop traffic
still routes retired ids; `/v1/daari/traces`, `/stats` and `/report` are
fleet-global with no team scoping (a tenant VK can read other teams' spend
when SSO is off); `daari backup create` embeds per-store sequential pg_dumps
with no shared snapshot (restored fleets can skew); every PG store connects
with a bare DSN and doctor never flags cleartext remote data planes; webhook
signing secrets are single-valued with no rotation grace.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 107 | Retired-model 410 on every facade (Ollama `/api/*`, decisions, embeddings, OCR, systemone) | 5 | 2 | OpenAI / LiteLLM uniform deny | 410 before burning Ollama/GPU on any door | Filed [#1676](https://github.com/naveenreddyalka/daari/issues/1676) |
| 108 | Team-scoped reads on /v1/daari traces, stats, report | 5 | 3 | Portkey / LiteLLM team dashboards | Rows already carry team_id; air-gapped RBAC | Filed [#1677](https://github.com/naveenreddyalka/daari/issues/1677) |
| 109 | Consistent cross-store backup: checkpoint + single PG snapshot | 5 | 4 | Managed Postgres PITR | App-consistent DR for air-gapped fleets | Filed [#1678](https://github.com/naveenreddyalka/daari/issues/1678) |
| 110 | Doctor + docs for TLS on remote Postgres/Redis data planes | 4 | 2 | Kong FIPS/TLS data planes | Refuse cleartext DSNs before keys leave the box | Filed [#1679](https://github.com/naveenreddyalka/daari/issues/1679) |
| 111 | Webhook signing-secret rotation with dual-secret grace | 4 | 2 | Stripe-style dual secrets | On-box rotate + audit row, no secrets manager | Filed [#1680](https://github.com/naveenreddyalka/daari/issues/1680) |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent on-box | Open [#1633] |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Open [#1634] |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open [#1640] |
| 78 | compare-litellm: LiteLLM 1.106 decision-model guardrail watch | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 97–101 | 10-14 wave: PG erasure; fail-closed PG auth/budget; lifecycle `shutdown_date`; MCP 429 audit; migrate/doctor PG | 4–5 | 2–4 | — / LiteLLM Alembic | Compliance + honest failure semantics on-box | Shipped |
| 102–106 | 10-14 eve wave: cache-invalidate audit + Grafana/alerts; Anthropic `decision` tag; mcp_servers config/Helm; error status labels | 3–4 | 1–3 | LiteLLM 1.107-dev Errors tab | Day-2 ops parity on-box | Shipped |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): PG request-log subject erasure;
fail-closed PG auth + budget degrade + `/ready`/doctor PG probes; shipped
OpenAI lifecycle waves + `shutdown_date`; MCP per-server 429 audit/Prom;
migrate/doctor PG schema visibility; cache-invalidate audit row +
Grafana/PrometheusRule; Anthropic-card `decision` capability; mcp_servers
rpm/tpm in config editor + Helm; `daari_errors_total` labeled by HTTP
status (stats/web-ui/Prom/alerts); stats-help, compare and virtual-keys
docs pins (72–74).

Watch rows (do not file yet): W3C `traceresponse` reply header + trace
continuity polish now that Anthropic SDKs trace by default (LiteLLM
1.107-dev parity; inbound `traceparent` extraction already shipped, #485);
runtime schema/version-skew guard + downgrade verb for rolling upgrades
(stamps exist only in migrate/backup; `/ready` has no version negotiation
— file on fleet-upgrade ask); `daari configure chatgpt-desktop` / `codex`
recipes (first-wave is claude-code/vscode/claude-desktop only); Responses
background completion webhooks + wider `include` allowlist (poll-only
today); Grafana errors-by-status panel (alert pack and stats already
labeled; dashboard still plots the aggregate); PG request-log concurrency/
soak coverage (memory-DSN unit tests only); HTTP admin API over the fleet
request/event log (`list_events` exists, unexposed — pairs with row 108);
per-key soft lockout on invalid-auth storms (IP throttle shipped; VK-level
not); Portkey v2.29 JWT claims→metadata conditional routing (file on
buyer ask); LiteLLM 1.107 GA watchables (Errors tab shipped in 106,
M365/GitHub Copilot OAuth providers, detect-only streamed guardrails,
deployment-warning endpoints, Helm DB/Redis from k8s Secret); SCIM +
multi-issuer/audience SSO; `gen_ai.agent.*` semconv; per-user
request-count RPD; Prometheus exemplars; Anthropic Managed Agents dynamic
workflows + Compliance API (non-goal); OpenAI in-product HIPAA BAA
(compliance non-goal).

Verified fine this run — don't re-audit: PG request-log erasure covers
gateway events (same table, erase deletes matching payloads; orchestrator
hooks it); fail-closed PG outage suite complete (auth/budgets/`/ready`/
doctor/docs); lifecycle 410 on chat + Anthropic messages + Responses (gap
is the other facades, row 107); `errors_by_status` flows through stats
CLI/API, web-ui and Prom labels with `sum(rate())` alerts; backup/restore
verbs incl. `--restore-pg` and PG request-log catalog row; revoked-jti
intentionally not backup-critical; session pins ephemeral by design;
invalid-key IP throttle + Prom `auth_throttled`; `daari audit verify`
hash-chain CLI; request logs carry no caller IP (private by default —
LiteLLM needed an opt-out flag); Redis clients default ~2s socket
timeouts; `daari spend export --team` on CLI.

---

## Path to enterprise-grade — next 5 milestones

1. **Uniform lifecycle enforcement** — retired 410 on every facade
   (row 107) so the shipped OpenAI calendar protects all doors, not three.
2. **Tenant-scoped observability** — team-scoped traces/stats/report
   (row 108), then the admin-plane rows (62–67) as sessions free up.
3. **Credible DR** — consistent cross-store backup with one PG snapshot
   (row 109); upgrade version-skew guard stays on watch behind it.
4. **Data-plane security floor** — TLS doctor checks for remote PG/Redis
   (row 110) and webhook secret rotation grace (row 111).
5. **Trace-native + onboarding polish** — `traceresponse` header,
   configure recipes for ChatGPT Desktop/Codex, Responses webhooks
   (watch rows → file as sessions open).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-15 (post-wave depth: lifecycle, tenancy, DR, data-plane TLS)** —
  Marked rows 97–106 Shipped (PRs #1663–#1672 drained both 10-14 tables in
  <24h; drained the dead eve sibling PRD PR to main). Filed rows 107–111:
  retired-410 facade completeness, team-scoped admin reads, consistent
  cross-store backup, remote PG/Redis TLS doctor checks, webhook
  signing-secret rotation grace. Outward: Anthropic OTel export beta
  (SDKs now trace Messages calls end-to-end), Portkey v2.29.0 (JWT
  claims→metadata routing, Decisions schema auto-detect, MCP traceparent),
  LiteLLM 1.107-dev watchables; Kong/vLLM/Ollama/OpenRouter/MCP flat.

- **2026-10-14 (overnight-wave parity depth)** — Filed rows 97–101 (PG
  erasure, PG outage semantics, model lifecycle, MCP 429 parity, migrate
  visibility). Eve sibling filed rows 102–106 (cache-invalidate ops,
  Anthropic decision tag, mcp_servers config/Helm, error status labels);
  its PRD PR failed the pin test and was drained to main 10-15.

- **2026-10-13 → 08-28** — Condensed: day-2 operations + observability
  packaging; concurrency + decision-guardrail depth; control-plane honesty
  + MCP server rpm; export honesty + doctor ACL; team DR + console
  lifecycle; RBAC floors + decisions agility; key/end-user lifecycle;
  admin-plane honesty; Decisions/OAuth/multi-agent; governance parity;
  LiteLLM 1.104; Apache 2.0; this PRD's creation.
