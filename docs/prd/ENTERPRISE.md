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

## Where daari stands (verified in-tree, 2026-10-25)

**Loop velocity.** Overnight/morning merges closed the 10-24 push-channel and
trust set: completion-webhook off-loop delivery, org enforcement ingest,
TTS body/input bounds, per-user RPD, Phonon voices, fleet-shared breakers,
Postgres `schema_ok`/`migrate --downgrade`, web-ui enforcement panel,
runtime eMudhra egress distrust, and compare-litellm 1.106.3. A morning
refill already stocked image-trust, gateway-flow coverage, FinOps
group-by, per-family breaker observability, and Anthropic `metadata.user_id`
attribution. This run hardens day-2 packaging around those channels and
opens local voice + skills honesty.

**Outward.** LiteLLM **1.106.4** (2026-10-25) is the new GA floor: cosign
key still `e82a3c6`; image-scan scrub for brotli 1.2.0 + **emSign ECC Root
CA - G3** (+ unused lockfile packages); proxy no longer ImportErrors when
the remote model-cost map is unreachable. **1.107.0** remains compromised /
do-not-install. Ollama **0.40.11** GA: Phonon speech on macOS, language
tags (`phonon:40m-fr|de|es|pt|multilingual`; 40M = CC BY-NC), d3 decision
models. Anthropic Managed Agents session threads + SSE (not Messages API
threads); AAIF Agent Skills package layout (`SKILL.md` in a directory).
vLLM 0.32.0, Kong AI Gateway 2.2 / 3.16.x, OpenRouter Private Endpoints,
semantic-router 0.4 / 1.x — flat. GPTCache / RouteLLM / OptiLLM — no
enterprise-relevant delta. certifi 2026.10.23 still ships eMudhra roots
(runtime filter shipped; image scrub still open).

**Inward theme: day-2 the push channels; speak every Phonon; load real
skills.** Completion-webhook doctor parity lags budget/key-expiry secret
checks. Webhook Prom counters exist with no Grafana/PromRule. Phonon
multilingual tags and CC BY-NC cliff are invisible. Skills loader is still
flat `*.md` only. Hermetic benchmarks never touch the TTS path. Image
trust store scrub and gateway-flow coverage for the wave remain the
morning P1/P2 spine.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 212 | Doctor: `responses_completion_webhook_url` without signing secret | 3 | 1 | LiteLLM / Svix webhook hygiene | Same doctor pass as budget/key-expiry | Filed [#1934](https://github.com/naveenreddyalka/daari/issues/1934) |
| 213 | Grafana + PrometheusRule for completion / org webhook counters | 3 | 1 | Kong / cloud webhook dashboards | Counters already exported; packaging | Filed [#1935](https://github.com/naveenreddyalka/daari/issues/1935) |
| 214 | Phonon multilingual tags + doctor CC BY-NC tip for 40m | 3 | 2 | OpenAI TTS / Ollama 0.40.11 | Local voice behind daari auth/budgets | Filed [#1936](https://github.com/naveenreddyalka/daari/issues/1936) |
| 215 | AAIF Agent Skills packages (`SKILL.md` in subdirs) | 3 | 2 | Claude / AAIF skill loaders | One on-disk tree for IDE + daemon | Filed [#1937](https://github.com/naveenreddyalka/daari/issues/1937) |
| 216 | Hermetic TTS speech micro-benchmark (stream finalize + voices) | 2 | 1 | — (testability) | Opt-in benchmark suite already hermetic | Filed [#1938](https://github.com/naveenreddyalka/daari/issues/1938) |
| 207 | Docker/image scrub of eMudhra/emSign + compare floor 1.106.4 | 4 | 1 | LiteLLM 1.106.4 images | Same filter policy at build time | Filed (morning refill) |
| 208 | Gateway-flow coverage for 10-24/25 wave | 3 | 2 | LiteLLM proxy integration suites | One hermetic file, no live Ollama | Filed (morning refill) |
| 209 | Dimension-grouped spend reports; persist `service_tier` | 3 | 2 | Anthropic Admin / LiteLLM leaderboards | Ledger already meters the dimensions | Filed (morning refill) |
| 210 | Per-family breaker state, alerts, reset (beyond systemone) | 3 | 2 | Kong upstream health | Redis-shared state already exists | Filed (morning refill) |
| 211 | Anthropic `metadata.user_id` → per-user fences; surface `user_rpd` | 3 | 2 | Anthropic Admin / OpenRouter | One ledger across both SDK doors | Filed (morning refill) |
| 206 | Client-visible content-strip warnings + Decisions reported-cost | 3 | 2 | OpenRouter / OpenAI usage-true | `daari_meta.warning` + counters exist | Open |
| 203–205 | Completion webhook delivery; org ingest; TTS bounds | 3–4 | 1–3 | OpenAI / Anthropic / Svix | Shipped | Shipped |
| 198–202 | eMudhra egress; fleet breakers; Phonon voices; compare 1.106.3; user_rpd | 3–4 | 1–3 | LiteLLM / Kong / OpenAI | Shipped (image scrub still 207) | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): Anthropic **Managed Agents** session-thread
proxy (SSE at `/v1/sessions/...` — buyer ask; not Messages API threads);
**Claude Models on Google Cloud** as a frontier flavor (IAM egress);
Open Responses WebSocket transport; Anthropic OTel export beta parity;
Prometheus exemplars + `gen_ai.agent.*`; Nemotron DFlash tip; LiteLLM
post-compromise 1.107-rebuild watchables (ID-JAG / OAuth-delegate /
`agent_access_default_deny`); Portkey WIF upstream creds; SCIM +
multi-issuer SSO; Kong Skills/A2A passthrough; OpenRouter Private
Endpoints as an L6 slot recipe.

Verified fine this run — don't re-audit: completion webhook off-loop +
Redis claim + previous-secret grace; org webhook `webhook-id` replay
dedupe + non-blocking profile fetch; TTS body/input caps carved out of
the 100 MB upload floor; runtime eMudhra filter on egress httpx;
fleet-shared breakers via Redis; Phonon English voice map + `/v1/audio/voices`;
`user_rpd` on top-level JSON `user`; served-tier billing incl. Anthropic
`speed` analog; Decisions GA fences; Anthropic SDK 2.x Bearer auth at
ingress.

---

## Path to enterprise-grade — next 5 milestones

1. **Close the trust/image floor** — scrub eMudhra/emSign from shipped
   image trust stores and pin compare-litellm at 1.106.4 (row 207).
2. **Day-2 the push channels** — doctor secret parity (212), Grafana/alerts
   for webhook counters (213); finish strip/billing honesty (206).
3. **Prove the wave** — gateway-flow coverage (208) + hermetic TTS
   benchmark (216).
4. **Speak and skill locally** — Phonon multilingual + license tip (214);
   AAIF `SKILL.md` packages (215).
5. **FinOps + HA observability + tenancy** — dimension-grouped spend (209),
   per-family breaker inventory (210), Anthropic user attribution (211),
   then the 10-10 tenancy set (62–67).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, Managed Agents proxy, full Open Responses WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-10-25 (day-2 the push channels; speak every Phonon; load real
  skills)** — Marked rows 198–205 Shipped (image scrub remains as 207).
  Outward: LiteLLM 1.106.4 GA floor (emSign image scrub + cost-map
  ImportError fix; 1.107 still do-not-install); Ollama 0.40.11 Phonon
  languages + CC BY-NC on 40m; AAIF Agent Skills package layout. Recorded
  morning refill rows 207–211. Filed rows 212–216: completion-webhook
  doctor secret check, webhook Grafana/alerts, Phonon multilingual +
  license tip, AAIF skills packages, hermetic TTS benchmark.

- **2026-10-24 pm (harden the push channels, protect the box)** — Filed
  rows 203–206. Outward: Anthropic SDK 2.2/2.3, Claude on Google Cloud,
  Bearer-auth switch verified at ingress.

- **2026-10-24 (match trust floors, finish HA share, speak local voice)** —
  Filed rows 198–202. Outward: LiteLLM 1.106.3; Ollama 0.40.10 / 0.40.11-rc0;
  AAIF Skills + Open Responses WS; Anthropic OTel beta.

- **2026-10-23 → 08-28** — Condensed: bill what was served; finish the
  truths / console / PG gate; breaker truth; invoice-true cache billing;
  LiteLLM compromise + Anthropic API-version footgun; Apache 2.0; this
  PRD's creation.
