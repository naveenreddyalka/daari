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

## Where daari stands (verified in-tree, 2026-10-13 eve)

**Loop velocity.** Morning filed rows 87–91 (alert pack, fleet request-log
backend, MCP proxy Prom, member budget webhooks, DEC/SYS bench docs) are
still open; 85–86 and docs pins 72–74/78 open; end-user/guardrail/web-ui/
report/multi-agent 62–63/65–67 still `agent:working`. Overnight 80–84 remain
Shipped.

**Outward.** LiteLLM **1.105.0 GA** (Decisions, `litellm.agent()`, Lens) +
1.106.0-rc.1; Portkey v2.28.0; Kong 2.2.0; Ollama 0.40.3 stable /
0.40.4-rc1 (llama.cpp b11521 decision models + EmbeddingGemma 2); vLLM
0.31.0; OpenRouter quiet since Oct 9; MCP blog Aug 22. compare-litellm still
calls 1.105 an RC — honesty gap.

**Inward theme: day-2 observability packaging.** Code audit: Helm ships
`ServiceMonitor` but **no** Grafana ConfigMap (JSON lives only under
`deploy/grafana/`); chart image refs are tag-only despite cosign-by-digest
publish; scoped `daari_in_flight{…}` gauges ship from concurrency caps but
the overview dashboard charts only the global gate; `cache_invalidate` is
JSONL-logged with **zero** Prom series. Alert pack + fleet log backend
(morning rows) still the durability/paging spine.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 92 | Helm opt-in ConfigMap for `deploy/grafana/daari-dashboard.json` | 4 | 2 | Kong / LiteLLM chart dashboards | One `helm install` lights on-box panels | Filed [#1636](https://github.com/naveenreddyalka/daari/issues/1636) |
| 93 | Helm optional `image.digest` pin (`repo@sha256`) for cosign promote | 4 | 2 | Regulated charts / LiteLLM signed images | Pin the blob you verified, not a floating tag | Filed [#1637](https://github.com/naveenreddyalka/daari/issues/1637) |
| 94 | Grafana panels for scoped `daari_in_flight` / `_max` (key/team/model) | 3 | 1 | LiteLLM concurrency admin UI | See which key saturates the GPU on-box | Filed [#1638](https://github.com/naveenreddyalka/daari/issues/1638) |
| 95 | Prom counter for cache invalidate ops (`l0`/`l1` removed, bounded labels) | 3 | 1 | LiteLLM Redis invalidation metrics | Page on surprise mass erase without shipping JSONL | Filed [#1639](https://github.com/naveenreddyalka/daari/issues/1639) |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs on-box multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first vs cloud agent control plane | Filed [#1640](https://github.com/naveenreddyalka/daari/issues/1640) |
| 87 | Shipped PrometheusRule alert pack: breaker/budget/5xx/queue/guardrails/key-expiry | 5 | 2 | LiteLLM alerting docs / Kong | Batteries-included day-2 ops on-box | Filed [#1630](https://github.com/naveenreddyalka/daari/issues/1630) |
| 88 | Fleet-durable request/event log backend (postgres\|redis) — last per-pod store | 5 | 4 | LiteLLM DB spend logs | Air-gapped fleets need on-box durability | Filed [#1631](https://github.com/naveenreddyalka/daari/issues/1631) |
| 89 | /mcp/proxy + MCP tasks Prom parity; register `mcp` modality (spans report `chat` today) | 4 | 2 | Kong MCP analytics / LiteLLM | One governed MCP door must be observable | Filed [#1632](https://github.com/naveenreddyalka/daari/issues/1632) |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent via the on-box ledger | Filed [#1633](https://github.com/naveenreddyalka/daari/issues/1633) |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Filed [#1634](https://github.com/naveenreddyalka/daari/issues/1634) |
| 85 | Advertise local decisions catalog on `/v1/models` + Ollama `/api/tags` | 3 | 2 | LiteLLM 1.106 decisions UI | BYOK clients discover on-box judges | Open |
| 86 | Per-server rpm/tpm ceilings on `integrations.mcp_servers` | 4 | 2 | LiteLLM MCP limits | Protect small MCP backends from one tenant | Open |
| 72 | `daari stats --help` mentions `virtual_keys` | 2 | 1 | — (CLI honesty) | Same JSON operators already dump | Open |
| 73 | compare-litellm: LiteLLM 1.105 Decisions vs daari (superseded by row 96 GA flip) | 2 | 1 | LiteLLM release notes | On-box Decisions already ship | Open |
| 74 | Hermetic pin: virtual-keys.md documents `/v1/models` allowlist | 2 | 1 | — (docs regression) | Keep ACL sentence in CI | Open |
| 78 | compare-litellm: LiteLLM 1.106 decision-model guardrail watch | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter guardrail assign / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 80–84 | Decision-guardrail data plane; teams metadata Postgres/export; concurrency-cap ops; Helm external egress + scheduling; hermetic RPM clock | 3–5 | 1–3 | Portkey / LiteLLM / Kong | — | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): decision-guardrail async data plane +
chat audit + kind metrics; teams metadata Postgres/export parity; concurrency
caps across CLI/admin/web-ui/Helm/Prom; Helm external Redis/Postgres egress +
scheduling knobs; hermetic RPM clock; audit rows for budget 402 and
rate-limit/concurrency rejects; systemone Idempotency-Key; teams export
`cache_scope`/`priority`; web-ui lifecycle columns + filters; bench
DEC-01/SYS-01; doctor empty-allowlist tip; analyst role floors; compact-to-fit
config/doctor/docs/meta/stats; MCP grant fail-closed + counters; Grafana
compact/MCP/decision panels.

Watch rows (do not file yet): SCIM provisioning + multi-issuer/audience SSO
(groups→team sync + revoke happen only at next login — file on
regulated-buyer ask); `gen_ai.agent.*` semconv spans for multi_agent
(conversation.id ships; agent spans on OTel semconv demand); per-user
request-count RPD beyond `user_daily_usd_cap` (buyer ask); Prometheus
exemplars on hand-rolled histograms (tracing-correlation ask); decisions
catalog pricing/capabilities for drex/microsoft ids ($0 local by design —
file if a hosted variant routes); gpt-6-luna Decisions schema drift;
OpenRouter BYOK `declared_region` / IP allowlists (buyer ask); Anthropic
Managed Agents / Compliance API (non-goal); Kong 2.2 MCP bundling +
modality cost (buyer ask); LiteLLM 1.106 GA Lens UI depth + M365 MCP catalog
(compare row 78 at GA; row 96 covers 1.105 agent framing only); Portkey JWT
JIT (operator ask); OpenAI in-product HIPAA BAA (compliance non-goal);
OpenAI 128-char safety identifiers doc (client-side); Redis pub/sub fanout
for disk-backend cache invalidate (file when multi-replica disk L0 returns).

Verified fine this run — don't re-audit: request-log rotation + retention
prune + stdout mirror + OTLP emit (gap is shared backend only); backup
catalogs request-log JSONL incl. rotated files; budget + key-expiry
webhooks signed and Redis-deduped; MCP ingress tools/call + egress Prom
counters; OCR/systemone/decisions Prom + OTel + ledger parity; multi-JWKS
SSO + groups→team sync + unmapped-deny revoke at login;
`gen_ai.conversation.id` from session_id; global concurrency-gate Grafana
panel (gap is **scoped** gauges only); ServiceMonitor bearer for /metrics;
cosign keyless publish path in `docker.yml` / RELEASING.md (gap is Helm
digest expression only).

---

## Path to enterprise-grade — next 5 milestones

1. **Alerting + dashboard packaging** — PrometheusRule pack (row 87) plus
   Helm Grafana ConfigMap (row 92) so scrape and panels arrive together.
2. **Fleet log durability** — request/event log on Postgres/Redis (row 88).
3. **Supply-chain pin + observable MCP** — image digest values (row 93);
   /mcp/proxy Prom + `mcp` modality (row 89); per-server MCP ceilings (86).
4. **Concurrency + invalidate truth** — scoped in_flight Grafana (row 94),
   invalidate Prom counter (row 95), member budget webhooks (row 90).
5. **Admin plane + proof** — end-user/guardrail profiles (62–63), web-ui/
   report bounds (65–66), cost-true multi_agent (67), decisions catalog +
   L0 bench (85, 91), compare 1.105 GA honesty (row 96).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-13 eve (day-2 observability packaging)** — Filed rows 92–96:
  Helm Grafana dashboard ConfigMap, optional `image.digest` pin, Grafana
  scoped `daari_in_flight` panels, Prom counter for cache invalidate,
  compare-litellm 1.105.0 GA + `litellm.agent()`/Lens vs on-box multi_agent.
  Outward: LiteLLM 1.105.0 confirmed GA (was still RC-framed in docs);
  Ollama 0.40.4-rc1. Morning rows 87–91 remain open. Collapsed shipped
  80–84 and older compact/MCP panel rows in the table.

- **2026-10-13 (day-2 operations depth)** — Marked rows 80–84 Shipped;
  adopted eve-sibling rows 85–86. Filed rows 87–91: PrometheusRule alert
  pack, fleet-durable request/event log, /mcp/proxy Prom + `mcp` modality,
  per-member budget webhooks, BENCHMARKS DEC/SYS + decisions L0-hit.
  Outward flat (LiteLLM 1.105.0 / Portkey 2.28.0 / Kong 2.2.0 / Ollama
  0.40.3 / vLLM 0.31.0). Watch: SCIM + multi-issuer SSO, gen_ai.agent.*,
  per-user RPD, Prom exemplars.

- **2026-10-12 (concurrency + decision-guardrail depth)** — Filed rows
  80–84; drained stale sibling PRD PR to main.

- **2026-10-12 eve (control-plane honesty + MCP server rpm)** — Sibling
  scan filed rows 85–86; PRD PR drained to main (rows adopted 10-13).

- **2026-10-11 → 08-28** — Condensed: export honesty + doctor ACL; team DR
  + console lifecycle + Decisions bench; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
