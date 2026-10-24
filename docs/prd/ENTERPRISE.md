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

## Where daari stands (verified in-tree, 2026-10-24)

**Loop velocity.** Ten feature PRs merged in the 24h since the last scan: the
whole 10-23 morning set (served-tier billing, Decisions GA parity, d3 + Flint,
streamed TTS, wave panels), both held-over HA items (fleet Responses cancel,
org enforcement webhook ingest), and three of the pm sibling's five
(document/citations strip, completion webhooks, Bolt E4B recipe). Open
backlog: the console + Postgres pair from the pm run, plus the 10-10
tenancy/console set (`agent:working`).

**Outward.** Anthropic SDK 2.2.0/2.3.0 (10-23): **message threads**,
**usage/cost reports grouped by dimension** (`model`/`speed`/`service_tier`/
`inference_geo`; legacy reports deprecated), Claude Tags (Slack-scoped).
**Claude Models on Google Cloud (Anthropic managed)** launched 10-22 — IAM
auth, Marketplace billing, fast mode included. New 2.x SDKs send
`Authorization: Bearer` instead of `X-Api-Key`; daari ingress already accepts
both and shape-detects on `anthropic-version`, so no break. Ollama 0.40.10 GA
(Bolt E4B); 0.40.11-rc0 adds a **Phonon voice catalog** and a d3 empty-state
fix. LiteLLM floor still 1.106.2 (canonical incident record posted 10-23).
Kong 2.2.0 / OpenRouter / vLLM 0.32.0 / Portkey 2.20 flat.

**Inward theme: harden the push channels the wave opened; protect the box.**
Completion webhooks post from a sync client inside the event loop, once, with
no fleet dedupe and no secret-rotation family. Org webhook ingest can be
replayed within the timestamp window to clear enforcement, blocks the loop on
a 15s Admin API fetch, and lands in a per-pod JSON file. Breakers beyond
systemone are still per-pod. `/v1/audio/speech` inherits the 100 MB upload
floor with no input cap. The #1904 strips are invisible to clients, and
Decisions discards provider-reported cost.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 203 | Completion webhook delivery: off-loop + retry, Prom counter, fleet dedupe, rotation family | 4 | 2 | OpenAI webhooks (72h retries) / Svix | Signed-deliver, Redis claim, soft-warning counters all in-tree — assembly, not infra | Filed [#1913](https://github.com/naveenreddyalka/daari/issues/1913) |
| 204 | Org enforcement webhook ingest: `webhook-id` replay dedupe, non-blocking profile fetch, audit + Prom, fleet-shared state | 4 | 3 | Anthropic / Svix (Standard Webhooks) / Kong cluster state | Redis `SET NX` idiom + enforcement store exist; truth stays fleet-wide | Filed [#1914](https://github.com/naveenreddyalka/daari/issues/1914) |
| 205 | Fleet-share frontier / local-pool / MCP egress circuit breakers via Redis | 4 | 3 | Kong cluster health / LiteLLM Redis cooldowns | Same Redis as L0/RL/lockout; doctor/stats/reset surfaces extend | Filed [#1915](https://github.com/naveenreddyalka/daari/issues/1915) |
| 206 | Bound `/v1/audio/speech`: carve out of 100 MB upload floor + `input` length cap | 3 | 1 | OpenAI (4096-char cap) | Protects the box that also hosts the models; OpenAI-shaped 400 pre-guardrail | Filed [#1916](https://github.com/naveenreddyalka/daari/issues/1916) |
| 207 | Client-visible content-strip warnings + Decisions reported-cost billing + live model-list 400 | 3 | 2 | OpenRouter transform warnings / OpenAI usage-true billing | `daari_meta.warning` + labeled counters exist; honesty end to end | Filed [#1917](https://github.com/naveenreddyalka/daari/issues/1917) |
| 201 | Web-ui: enforcement inventory panel + cache-invalidate admin form | 3 | 2 | LiteLLM admin UI | HTTP/CLI exist; console finishes day-2 | Open ([#1894](https://github.com/naveenreddyalka/daari/issues/1894)) |
| 202 | Postgres `schema_ok` skew gate on `/ready` + `migrate --downgrade` | 3 | 2 | Cloud gateway migrate tooling | SQLite already gates; PG buyers need parity | Open ([#1895](https://github.com/naveenreddyalka/daari/issues/1895)) |
| 191–200 | 10-23 → 10-24 waves: fleet Responses cancel; enforcement webhook ingest; served-tier billing; Decisions GA; d3 + Flint; streamed TTS; wave panels; document/citations strip; completion webhooks; Bolt E4B recipe | 3–4 | 1–3 | OpenAI / Anthropic / Ollama / Grafana | Invoice truth, push, $0 judge tier, local voice | Shipped |
| 183–190 | 10-22 waves: streamed cache-write TTL billing; enforcement sync; service-tier degrade; Redis breaker; sampling-strip telemetry; console export/reset; gzip + TTL panels; vLLM floor doc | 3–4 | 1–3 | OpenAI / Anthropic / Kong / LiteLLM | Invoice, blast-radius, HA, day-2 truths | Shipped |
| 136–182 | 10-18 → 10-21 waves (protocol, egress, FinOps, judge ops) | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Local-first parity | Shipped |
| 62–67 | End-user inventory; guardrail profiles; web-ui keys/teams/`report.users`; bound report rollups; multi_agent nested `model` | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger + console already partial | Open (`agent:working`) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): hermetic gateway-flow coverage for the wave —
zero `test_gateway_flow.py` cases for streamed TTS, completion webhooks, org
webhook ingest, decisions `input_json`/images, or Anthropic stream
`cache_creation_input_tokens` → spend (next test audit; strip-warning assert
folded into row 207); **dimension-grouped usage/cost report export** over the
spend ledger (time buckets + `group_by` model/speed/tier/team — Anthropic
Admin API parity, SDK 2.2.0 marks legacy reports; file on FinOps ask);
Anthropic **message threads** (SDK 2.2.0; API shape undocumented — file when
docs land); **Claude Models on Google Cloud** as a frontier flavor (IAM-auth
egress — buyer ask); Ollama 0.40.11-rc0 Phonon **voice catalog** + d3
empty-state (file at GA); eMudhra CA distrust — certifi still ships emSign
roots (act when dropped or buyer pins `TLS_CA`); LiteLLM clean-rebuild
watchables (ID-JAG/OAuth-delegate, `agent_access_default_deny`); Portkey 2.20
WIF upstream creds; per-user RPD; SCIM + multi-issuer SSO; Prometheus
exemplars + `gen_ai.agent.*`.

Verified fine this run — don't re-audit: served-tier billing correct on both
paths incl. the Anthropic `speed` analog (`router.py` ~L1330/3128); fleet
cancel fires no duplicate completion webhook (terminal short-circuit +
cancel-check before notify, Redis flag TTL 1h); Decisions GA fences complete
(400-question cap, stream reject, `input_json` validation, L0 fingerprint
incl. image parts, cached-input billing, d3 in catalog + pricing card);
streamed TTS finalizes spend/ledger with real byte count in the generator
`finally`, guardrails pre-relay, $0 local tier billing; org webhook signature
constant-time with previous-secret grace and 404 when unconfigured; #1903
panels/alerts present in both dashboard copies + PrometheusRule; #1904 strip
covers stream + non-stream + Responses-via-router, keeps nested tool-result
documents and `citations: {enabled}` config; Anthropic SDK 2.x
`Authorization: Bearer` switch already handled at ingress (`auth.py`,
`wants_anthropic_models` keys on `anthropic-version`).

---

## Path to enterprise-grade — next 5 milestones

1. **Harden the push channels** — completion-webhook delivery semantics (row
   203) and replay-safe, fleet-true org webhook ingest (row 204).
2. **Fleet-true breaker state** — share frontier/local-pool/MCP breakers over
   the Redis that HA deployments already run (row 205).
3. **Protect the box, finish the honesty** — bound the TTS door (row 206);
   client-visible strips + reported-cost Decisions billing (row 207).
4. **Console + Postgres parity** — enforcement inventory and cache invalidate
   in the web-ui (row 201); PG schema gate + migrate downgrade (row 202).
5. **Drain the tenancy/FinOps queue** — the 10-10 set (rows 62–67), then
   dimension-grouped spend reports when a FinOps buyer asks.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-24 (harden the push channels; protect the box)** — Marked rows
  191–200 Shipped (ten PRs in 24h: the 10-23 morning five, fleet cancel,
  webhook ingest, and three pm rows; the stale pm PRD PR was drained by
  taking main). Outward: Anthropic SDK 2.2.0/2.3.0 (message threads,
  dimension-grouped usage/cost reports, Claude Tags), Claude on Google Cloud,
  Bearer-auth SDK switch (handled at ingress); Ollama 0.40.10 GA +
  0.40.11-rc0 voice catalog; LiteLLM floor still 1.106.2. Filed rows
  203–207: completion-webhook delivery semantics, replay-safe webhook
  ingest, fleet-shared breakers, TTS input bound, strip/billing honesty.

- **2026-10-23 + pm (bill what was served, speak what went GA; API-version
  footgun, completion push, console, PG gate)** — Marked rows 183–190
  Shipped. Filed rows 193–197 (served-tier billing, Decisions GA parity,
  d3 + Flint recipe, streamed TTS, wave observability) and 198–202
  (document/citations strip, completion webhooks, Bolt E4B recipe, web-ui
  enforcement console, PG schema gate). Outward: Ollama 0.40.9/0.40.10
  (Phonon speech, d3 decision models, Flint cross-platform, Bolt E4B);
  OpenAI Decisions GA; eMudhra CA distrust; semantic-router 1.0/1.1.

- **2026-10-22 + pm (finish the truths the wave started; console and day-2
  packaging)** — Marked rows 171–182 Shipped. Filed rows 183–192. Outward:
  LiteLLM compromise post-mortem (clean floor 1.106.2); Anthropic
  enforcement_status; OpenAI service-tier restrictions; Ollama 0.40.8 GA;
  vLLM 0.32.0 security wave.

- **2026-10-21 → 08-28** — Condensed: breaker truth, invoice-true cache
  billing, user profiles, LiteLLM 1.107 compromise, Anthropic `2026-10-21`
  sampling removal; finish-the-knobs; decisions-upstream depth; fast-mode
  cache truth; `resultType`/egress/billing waves; lifecycle/tenancy/DR;
  LiteLLM 1.104–1.106; Apache 2.0; this PRD's creation.
