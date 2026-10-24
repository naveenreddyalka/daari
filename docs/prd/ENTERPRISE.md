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

## Where daari stands (verified in-tree, 2026-10-24 pm)

**Loop velocity.** Ten feature PRs merged in 24h: served-tier billing,
Decisions GA parity, d3+Flint, streamed Phonon TTS, wave Grafana alerts,
fleet Responses cancel, enforcement webhook ingest, signed Responses
completion webhooks, Anthropic 2026-10-21 document/citation strips, and the
Nemotron 3.5 Bolt E4B VLM recipe. The backlog was refilled twice today
(morning rows 198–202, pm rows 203–206) on top of the console enforcement
panel, Postgres `schema_ok`/`migrate --downgrade`, and the 10-10 tenancy set.

**Outward.** LiteLLM **1.106.3** (2026-10-24) is the new GA floor: cosign
signing key rotated to commit `e82a3c6`, and the **eMudhra root CA is
removed** from every LiteLLM trust bundle (backported to 1.103.8 / 1.104.6 /
1.105.4). Treat **1.107.0** as still compromised / do-not-install. Anthropic
SDK **2.2.0/2.3.0** (10-23): **message threads**, **usage/cost reports
grouped by dimension** (`model`/`speed`/`service_tier`/`inference_geo`;
legacy reports deprecated), Claude Tags (Slack-scoped). **Claude Models on
Google Cloud (Anthropic managed)** launched 10-22 — IAM auth, Marketplace
billing, fast mode included. New 2.x SDKs send `Authorization: Bearer`
instead of `X-Api-Key`; daari ingress accepts both and shape-detects on
`anthropic-version`, so no break. Ollama **0.40.10** GA; **0.40.11-rc0**
adds a Phonon voice catalog + mlxrunner spelling for symbols/numbers/links.
AAIF (10-22) took Agent Skills, Open Responses (adds WebSocket + compaction),
OpenEnv, OpenSandbox. Anthropic OTel export for Messages is in beta. vLLM
0.32.0, Kong 3.16.0.1 (A2A v1.0), semantic-router 1.0/1.1, OpenRouter
Private Endpoints — flat. certifi 2026.10.23 still ships eMudhra roots.

**Inward theme (pm): harden the push channels the wave opened; protect the
box.** Completion webhooks post from a sync client inside the event loop,
once, with no fleet dedupe and no secret-rotation family. Org webhook ingest
can be replayed within the timestamp window to clear enforcement, blocks the
loop on a 15s Admin API fetch, and lands in a per-pod JSON file. Breakers
beyond systemone are still per-pod (morning row 199). `/v1/audio/speech`
inherits the 100 MB upload floor with no input cap. The strips are invisible
to clients, and Decisions discards provider-reported cost.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 203 | Completion webhook delivery: off-loop + retry, Prom counter, fleet dedupe, rotation family | 4 | 2 | OpenAI webhooks (72h retries) / Svix | Signed-deliver, Redis claim, soft-warning counters all in-tree — assembly, not infra | Filed [#1913](https://github.com/naveenreddyalka/daari/issues/1913) |
| 204 | Org enforcement webhook ingest: `webhook-id` replay dedupe, non-blocking profile fetch, audit + Prom, fleet-shared state | 4 | 3 | Anthropic / Svix (Standard Webhooks) / Kong cluster state | Redis `SET NX` idiom + enforcement store exist; truth stays fleet-wide | Filed [#1914](https://github.com/naveenreddyalka/daari/issues/1914) |
| 205 | Bound `/v1/audio/speech`: carve out of 100 MB upload floor + `input` length cap | 3 | 1 | OpenAI (4096-char cap) | Protects the box that also hosts the models; OpenAI-shaped 400 pre-guardrail | Filed [#1916](https://github.com/naveenreddyalka/daari/issues/1916) |
| 206 | Client-visible content-strip warnings + Decisions reported-cost billing + live model-list 400 | 3 | 2 | OpenRouter transform warnings / OpenAI usage-true billing | `daari_meta.warning` + labeled counters exist; honesty end to end | Filed [#1917](https://github.com/naveenreddyalka/daari/issues/1917) |
| 198 | Distrust eMudhra/emSign on egress TLS + doctor tip | 4 | 1 | LiteLLM 1.106.3 / Kong / Portkey | One-process TLS policy; no cloud image wait | Filed [#1907](https://github.com/naveenreddyalka/daari/issues/1907) |
| 199 | Fleet-share frontier / local-pool / MCP egress breakers via Redis | 4 | 3 | Kong / cloud gateways | Same Redis as cache; blast-radius on-box | Filed [#1908](https://github.com/naveenreddyalka/daari/issues/1908) (dup [#1915](https://github.com/naveenreddyalka/daari/issues/1915) needs human close) |
| 200 | Phonon voice catalog list + OpenAI voice-name map | 3 | 2 | OpenAI TTS / Ollama 0.40.11-rc0 | Local voices behind daari auth/budgets | Filed [#1909](https://github.com/naveenreddyalka/daari/issues/1909) |
| 201 | compare-litellm: pin GA floor at 1.106.3 (cosign + eMudhra) | 3 | 1 | LiteLLM release notes | Honest GTM without a LiteLLM runtime dep | Filed [#1910](https://github.com/naveenreddyalka/daari/issues/1910) |
| 202 | Per-end-user RPD alongside `user_daily_usd_cap` | 4 | 2 | LiteLLM / OpenRouter | Ledger already attributes `user` | Filed [#1911](https://github.com/naveenreddyalka/daari/issues/1911) |
| 193–197 | Served-tier spend; Decisions GA; d3+Flint; streamed TTS; wave panels/alerts | 3–4 | 1–2 | OpenAI / Ollama / Grafana | Invoice, GA shape, $0 judge, local voice, day-2 | Shipped |
| 191–192 | Fleet Responses cancel; Anthropic enforcement webhook ingest | 4 | 3 | OpenAI / Anthropic Admin | Redis cancel; push→tenant map | Shipped |
| 188–190 | Console export/reset; Grafana gzip+TTL; vLLM 0.32.0 floor doc | 3 | 1–2 | LiteLLM UI / Grafana / vLLM | Day-2 packaging | Shipped |
| — | Web-ui enforcement inventory + cache-invalidate form | 3 | 2 | LiteLLM admin UI | Same-box console | Open (filed prior run) |
| — | Postgres `schema_ok` skew gate + `migrate --downgrade` | 3 | 2 | LiteLLM migrate story | Ready truth for PG fleets | Open (filed prior run) |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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
| 136–182 | 10-18 → 10-21 protocol/FinOps/HA waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Shipped | Shipped |

Watch rows (do not file yet): hermetic **gateway-flow coverage for the wave**
— zero `test_gateway_flow.py` cases for streamed TTS, completion webhooks,
org webhook ingest, decisions `input_json`/images, or Anthropic stream
`cache_creation_input_tokens` → spend (next test audit; strip-warning assert
folded into row 206); **dimension-grouped usage/cost report export** over the
spend ledger (time buckets + `group_by` model/speed/tier/team — Anthropic
Admin API parity; file on FinOps ask); Anthropic **message threads** (SDK
2.2.0; API shape undocumented — file when docs land); **Claude Models on
Google Cloud** as a frontier flavor (IAM-auth egress — buyer ask); AAIF
Agent Skills package loader beyond flat `~/.daari/skills/*.md`; Open
Responses WebSocket transport; Anthropic OTel export beta parity; Prometheus
exemplars + `gen_ai.agent.*`; Nemotron DFlash tip once 0.40.10 recipes
settle; LiteLLM post-compromise 1.107-rebuild watchables (ID-JAG /
OAuth-delegate / `agent_access_default_deny`); Portkey WIF upstream creds;
per-user RPD now filed (row 202); SCIM + multi-issuer SSO; Kong Skills/A2A
passthrough demand; OpenRouter Private Endpoints as an L6 slot recipe.

Verified fine this run — don't re-audit: served-tier billing correct on both
paths incl. the Anthropic `speed` analog (`router.py` ~L1330/3128); fleet
cancel fires no duplicate completion webhook (terminal short-circuit +
cancel-check before notify, Redis flag TTL 1h); Decisions GA fences complete
(400-question cap, stream reject, `input_json` validation, L0 fingerprint
incl. image parts, cached-input billing, d3 in catalog + pricing card);
streamed TTS finalizes spend/ledger with real byte count in the generator
`finally`, guardrails pre-relay, $0 local-tier billing; org webhook signature
constant-time with previous-secret grace, 404 when unconfigured; #1903
panels/alerts in both dashboard copies + PrometheusRule; #1904 strip covers
stream + non-stream + Responses-via-router, keeps nested tool-result
documents and `citations: {enabled}`; Anthropic SDK 2.x `Authorization:
Bearer` switch handled at ingress (`auth.py`, `wants_anthropic_models` keys
on `anthropic-version`); cache-write TTL billing on stream shapes.

---

## Path to enterprise-grade — next 5 milestones

1. **Harden the push channels** — completion-webhook delivery semantics
   (row 203) and replay-safe, fleet-true org webhook ingest (row 204).
2. **Match the trust floors** — eMudhra distrust on egress + doctor tip
   (row 198); refresh compare-litellm to 1.106.3 (row 201).
3. **Finish HA share, protect the box** — fleet-shared breakers (row 199);
   bound the TTS door (row 205).
4. **Honesty + local voice** — client-visible strips and reported-cost
   Decisions billing (row 206); Phonon voice catalog (row 200).
5. **End-user fences, console, PG parity** — per-user RPD (row 202), the
   prior-run console/PG pair, then the 10-10 tenancy set (62–67) and
   dimension-grouped spend reports when a FinOps buyer asks.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, full AAIF Skills/Open Responses WS) stay deferred
until buyer demand.

---

## Changelog

- **2026-10-24 pm (harden the push channels, protect the box)** — Delta scan
  after the morning run: filed rows 203–206 (completion-webhook delivery
  semantics, replay-safe webhook ingest, TTS input bound, strip/billing
  honesty); the pm breaker filing was a duplicate of morning row 199 and
  needs a human close. Outward adds: Anthropic SDK 2.2.0/2.3.0 (message
  threads, dimension-grouped usage/cost reports, Claude Tags), Claude on
  Google Cloud, Bearer-auth SDK switch verified handled at ingress. Drained
  the stale 10-23 pm PRD PR by taking main.

- **2026-10-24 (match trust floors, finish HA share, speak local voice)** —
  Marked rows 191–197 Shipped (served-tier billing through Nemotron recipe
  and the HA/webhook/strip set all on main). Outward: LiteLLM 1.106.3 GA
  floor (cosign `e82a3c6`, eMudhra CA removed; 1.107 still do-not-install);
  Ollama 0.40.10 / 0.40.11-rc0 Phonon voice catalog; AAIF Skills + Open
  Responses WS; Anthropic OTel beta. Filed rows 198–202: eMudhra distrust,
  fleet-shared breakers, Phonon voices, compare-litellm 1.106.3, per-user
  RPD.

- **2026-10-23 (bill what was served, speak what went GA)** — Marked rows
  183–190 Shipped. Outward: Ollama 0.40.9; OpenAI Decisions GA; eMudhra
  distrust watch; semantic-router 1.0/1.1. Filed rows 193–197.

- **2026-10-22 + pm (finish the truths; console and day-2 packaging)** —
  Marked 171–182 Shipped. Filed 183–192. Outward: LiteLLM compromise
  post-mortem (floor 1.106.2); Anthropic enforcement_status; OpenAI
  service-tier restrictions; Ollama 0.40.8; vLLM 0.32.0.

- **2026-10-21 → 08-28** — Condensed: breaker truth, invoice-true cache
  billing, user profiles; LiteLLM compromise + Anthropic API-version
  footgun; finish-the-knobs; decisions depth; `resultType`/egress waves;
  Apache 2.0; this PRD's creation.
