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

## Where daari stands (verified in-tree, 2026-10-15 eve)

**Loop velocity.** Morning post-wave scan (rows 107–111) is still open on
main; earlier 10-14 tables (97–106) remain Shipped. This eve pass promotes
watch-list depth behind that wave: trace round-trip, admin request-log API,
per-key auth lockout, Grafana errors-by-status packaging, and ChatGPT
Desktop configure.

**Outward.** **LiteLLM v1.107.0-dev.2 (2026-10-15)**: Claude Code
`installationPreference`, team-scoped `/global/activity/cache_hits`,
decision models in AI Hub, classifier `safeguard_results` on the messages
bridge, DashScope video via `/v1/videos`; stable still 1.105.1 /
1.106.0-rc.4. **Anthropic OTel** remains the trace pressure (inbound
`traceparent` parents; `traceresponse` still missing). Portkey enterprise
notes JWT fail-closed hardening (v2.20 line); Kong AI Gateway 2.2.0 /
Operator 2.3 flat vs morning. **Ollama 0.40.4**: decision models in CLI +
`ollama launch codex`. OpenRouter Oct 9 filters / ElevenLabs audio — no
daari action this run. vLLM 0.31.0 flat.

**Inward theme: close the loop on shipped labels.** `errors_by_status` and
Prom labels shipped without a Grafana breakout; IP invalid-key throttle
ships without per-key lockout; `list_events` exists with no HTTP admin;
OTel extracts `traceparent` but never replies `traceresponse`; ChatGPT
Desktop has a manual guide but no `daari configure` recipe in the client
registry.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 112 | W3C `traceresponse` reply header on gateway responses | 5 | 2 | LiteLLM 1.107-dev / W3C Trace Context | Round-trip on-box once Anthropic SDKs arrive traced | Filed [#1682](https://github.com/naveenreddyalka/daari/issues/1682) |
| 113 | HTTP `GET /v1/daari/events` over fleet request/event log | 4 | 3 | LiteLLM activity / spend APIs | `list_events` already local; auth-gate it | Filed [#1683](https://github.com/naveenreddyalka/daari/issues/1683) |
| 114 | Per-key soft lockout on invalid-auth storms | 4 | 2 | OpenRouter Security Center / LiteLLM key risk | Same Redis/IP throttle pattern, keyed by VK | Filed [#1684](https://github.com/naveenreddyalka/daari/issues/1684) |
| 115 | Grafana panel: `daari_errors_total` by status | 3 | 1 | LiteLLM Errors tab | Labels already on Prom; packaging only | Filed [#1685](https://github.com/naveenreddyalka/daari/issues/1685) |
| 116 | `daari configure chatgpt-desktop` Ollama-facade recipe | 4 | 2 | Ollama Desktop / `ollama launch` | One-shot 11435 host; registry gap only | Filed [#1686](https://github.com/naveenreddyalka/daari/issues/1686) |
| 107 | Retired-model 410 on every facade (Ollama `/api/*`, decisions, embeddings, OCR, systemone) | 5 | 2 | OpenAI / LiteLLM uniform deny | 410 before burning Ollama/GPU on any door | Open |
| 108 | Team-scoped reads on /v1/daari traces, stats, report | 5 | 3 | Portkey / LiteLLM team dashboards | Rows already carry team_id; air-gapped RBAC | Open |
| 109 | Consistent cross-store backup: checkpoint + single PG snapshot | 5 | 4 | Managed Postgres PITR | App-consistent DR for air-gapped fleets | Open |
| 110 | Doctor + docs for TLS on remote Postgres/Redis data planes | 4 | 2 | Kong FIPS/TLS data planes | Refuse cleartext DSNs before keys leave the box | Open |
| 111 | Webhook signing-secret rotation with dual-secret grace | 4 | 2 | Stripe-style dual secrets | On-box rotate + audit row, no secrets manager | Open |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent on-box | Open |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Open |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 78 | compare-litellm: LiteLLM 1.106 decision-model guardrail watch | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 97–106 | 10-14 waves (PG erasure/outage; lifecycle; MCP 429; migrate; cache-invalidate; decision tag; mcp_servers Helm; error status labels) | 3–5 | 1–4 | — / LiteLLM | Compliance + day-2 ops on-box | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): PG request-log subject erasure;
fail-closed PG auth + budget degrade + `/ready`/doctor PG probes; shipped
OpenAI lifecycle waves + `shutdown_date`; MCP per-server 429 audit/Prom;
migrate/doctor PG schema visibility; cache-invalidate audit row +
Grafana/PrometheusRule; Anthropic-card `decision` capability; mcp_servers
rpm/tpm in config editor + Helm; `daari_errors_total` labeled by HTTP
status (stats/web-ui/Prom/alerts — **panel** still pending, row 115);
stats-help, compare and virtual-keys docs pins.

Watch rows (do not file yet): runtime schema/version-skew guard +
downgrade verb for rolling upgrades (stamps exist only in migrate/backup;
`/ready` has no version negotiation — file on fleet-upgrade ask behind
row 109); Responses background completion webhooks + wider `include`
allowlist (poll-only today); PG request-log concurrency/soak coverage
(memory-DSN unit tests only); Portkey JWT claims→metadata conditional
routing (file on buyer ask); LiteLLM 1.107 GA watchables (Errors tab
panel filed as 115; M365/GitHub Copilot OAuth providers, detect-only
streamed guardrails, deployment-warning endpoints, Helm DB/Redis from
k8s Secret, team-scoped analytics — tenancy row 108); Codex configure
recipe after chatgpt-desktop (row 116); SCIM + multi-issuer/audience SSO;
`gen_ai.agent.*` semconv; per-user request-count RPD; Prometheus
exemplars; Anthropic Managed Agents dynamic workflows + Compliance API
(non-goal); OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: inbound `traceparent` extract +
frontier inject (#485); IP invalid-key throttle + Prom `auth_throttled`;
`list_events` + subject erasure on PG request-log; `errors_by_status` in
stats/Prom/alerts; client registry has claude-code/desktop, cursor,
intellij, vscode only; retired 410 on chat/messages/responses (other
facades = row 107); backup/restore verbs incl. `--restore-pg`;
`daari audit verify` hash-chain CLI; Redis clients default ~2s socket
timeouts; `daari spend export --team` on CLI.

---

## Path to enterprise-grade — next 5 milestones

1. **Uniform lifecycle enforcement** — retired 410 on every facade
   (row 107) so the shipped OpenAI calendar protects all doors.
2. **Trace-native round-trip** — `traceresponse` (row 112) so Anthropic
   SDK / OTel clients get a complete on-box hop.
3. **Tenant-scoped + event admin plane** — team-scoped traces/stats/report
   (row 108) plus `GET /v1/daari/events` (row 113); then admin rows 62–67.
4. **Credible DR + data-plane floor** — cross-store backup (row 109),
   remote PG/Redis TLS doctor (row 110), webhook secret rotation (row 111),
   per-key auth lockout (row 114).
5. **Day-2 packaging + onboarding** — Grafana errors-by-status (row 115),
   chatgpt-desktop configure (row 116), then Codex recipe / version-skew
   watch rows as sessions open.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-15 (eve: traceresponse, events API, key lockout, Grafana, chatgpt-desktop)** —
  Filed rows 112–116 from watch-list promotion after morning 107–111.
  Outward: LiteLLM 1.107.0-dev.2 (team-scoped cache analytics, decision
  Hub, safeguard_results, DashScope video); Ollama 0.40.4 decision CLI +
  `launch codex`; Anthropic OTel still driving traceresponse; Portkey JWT
  fail-closed notes; Kong/vLLM/OpenRouter flat for filing.

- **2026-10-15 (post-wave depth: lifecycle, tenancy, DR, data-plane TLS)** —
  Marked rows 97–106 Shipped. Filed rows 107–111: retired-410 facade
  completeness, team-scoped admin reads, consistent cross-store backup,
  remote PG/Redis TLS doctor checks, webhook signing-secret rotation grace.
  Outward: Anthropic OTel export beta, Portkey v2.29 JWT claims→metadata,
  LiteLLM 1.107-dev watchables.

- **2026-10-14 (overnight-wave parity depth)** — Filed rows 97–101 (PG
  erasure, PG outage semantics, model lifecycle, MCP 429 parity, migrate
  visibility). Eve sibling filed rows 102–106 (cache-invalidate ops,
  Anthropic decision tag, mcp_servers config/Helm, error status labels).

- **2026-10-13 → 08-28** — Condensed: day-2 operations + observability
  packaging; concurrency + decision-guardrail depth; control-plane honesty
  + MCP server rpm; export honesty + doctor ACL; team DR + console
  lifecycle; RBAC floors + decisions agility; key/end-user lifecycle;
  admin-plane honesty; Decisions/OAuth/multi-agent; governance parity;
  LiteLLM 1.104; Apache 2.0; this PRD's creation.
