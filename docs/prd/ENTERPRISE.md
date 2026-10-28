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

## Where daari stands (verified in-tree, 2026-10-28)

**Loop velocity.** The whole 10-27 board merged within a day: d1 catalog
(PR #1989), Helm at-rest `secretKeyRef` (#1990), sealed files/batches
(#1991), SEP-2640 skills conformance (#1992), and the 10-26/27 wave fence
(#1993). Open work is now the Ollama-0.40.12 ride-along (rows 233–235),
the P3 honesty tail (rows 225–226, 236 + older voices/skills/TTS counters),
and today's Portkey-parity + llama.cpp set (rows 237–241).

**Outward.** Two real moves. **llama.cpp v0.8.0** (10-28) is the project's
first semver release: server gains `/v1/realtime` (OpenAI realtime
protocol) and `POST /tts`, chat gains deferred tools + `tool_reference`
parts, and the LFM3 family (text/vl/audio/omni) plus Liquid AI **d1-2B /
d1-omni** run on every platform — while Ollama 0.40.12 GA (10-27) ships
those same models **Apple-hardware-only**. **Portkey/Prisma AIRS
v2.31.0** (10-23 — prior "newest = v2.20.0" note was stale; v2.30.x shipped
the eMudhra trust-store update 10-22): Signals beta (pre-routing request
facts + conditional routing), claim-based JWT policies, custom guardrail
denial messages, per-MCP-integration timeouts, opt-in workspace label on
Prometheus. Flat: LiteLLM 1.106.5 (one logging backport), OpenAI ends
10-26 Terra (priced in-tree), Anthropic 10-23 Claude Tag beta (non-goal),
Kong 2.2.0, vLLM 0.32.0. OpenRouter 10-27: IAM-role auth for S3
observability destinations, private-endpoint declared/tested parameters.

**Inward theme: match the parts of Portkey v2.31.0 that daari already owns.**
daari computes richer request facts than Portkey's Signals but hides them;
it has one guardrail denial sentence for every rule; its MCP egress
timeout is a hardcoded 30s; its traffic Prom series have no team
dimension. Each is a small, on-box win. And llama.cpp v0.8.0 is now the
way to run LFM3/d1 on Linux — the docs should say so.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 237 | Per-rule custom guardrail denial messages | 3 | 1 | Portkey v2.31.0 custom errors | Operator-owned denial copy, evaluated on-box | Filed [#1994](https://github.com/naveenreddyalka/daari/issues/1994) |
| 238 | Per-server MCP egress request timeout | 3 | 1 | Portkey per-integration timeouts | Tune each local hop; honest breaker signals | Filed [#1995](https://github.com/naveenreddyalka/daari/issues/1995) |
| 239 | Request-fact signals in `daari_meta` + opt-in signal overrides | 4 | 3 | Portkey Signals beta | Facts already computed free on-box; no SaaS classifier | Filed [#1996](https://github.com/naveenreddyalka/daari/issues/1996) |
| 240 | Opt-in `team` label on requests/errors Prom series | 3 | 2 | Portkey `PROMETHEUS_EXTRA_LABELS` | Per-team traffic scraped on-box, no analytics tier | Filed [#1997](https://github.com/naveenreddyalka/daari/issues/1997) |
| 241 | llama.cpp v0.8.0 local-tier guide + landscape refresh | 2 | 1 | llama.cpp release notes | Linux path to LFM3/d1 today; honest watch list | Filed [#1998](https://github.com/naveenreddyalka/daari/issues/1998) |
| 233 | Optional LFM3 L3 setup recipe (256K local agent tier) | 3 | 2 | Ollama `ollama run lfm3` | One `daari setup models` prompt, on-box | Filed [#1984](https://github.com/naveenreddyalka/daari/issues/1984) |
| 234 | Doctor tip when Ollama serves d1/lfm3 but catalog/recipes unused | 3 | 1 | — (ops honesty) | Point at the local win before L6 | Filed [#1985](https://github.com/naveenreddyalka/daari/issues/1985) |
| 235 | Recognize `lfm3-audio` as local ASR/TTS backend beside Phonon | 3 | 2 | Ollama speech / Phonon | 18-language local speech without cloud | Filed [#1986](https://github.com/naveenreddyalka/daari/issues/1986) |
| 236 | Prometheus + stats counter for decisions L0 cache hits | 2 | 1 | LiteLLM spend / cache tabs | Local judgment reuse is scrapeable | Filed [#1987](https://github.com/naveenreddyalka/daari/issues/1987) |
| 225 | `daari_schema_ok` HELP + Grafana copy cover Postgres skew | 2 | 1 | — (ops honesty) | Gauge already right; text lagged | Filed [#1966](https://github.com/naveenreddyalka/daari/issues/1966) |
| 226 | Prometheus counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform metrics | Local scrape next to the TTS path | Filed [#1967](https://github.com/naveenreddyalka/daari/issues/1967) |
| 227–232 | 10-27 wave: Helm at-rest `secretKeyRef`, sealed files/batches, SEP-2640 conformance, wave fence, d1 catalog | 2–4 | 1–2 | LiteLLM / OpenAI EKM / MCP SDK | Sealed payloads + discoverable on-box skills | Shipped (231 Prom tail → open #1981) |
| 217–224 | 10-26 waves: job lease/heartbeat + reclaim, at-rest encryption, Helm webhook knobs, wave fence, coercion warning, Terra day-one rates, grouped-report UI, SEP-2640 skills/list | 2–4 | 1–3 | OpenAI / LiteLLM / Bloomberg | HA jobs, EKM analog, push story, FinOps truth | Shipped |
| 198–216 | 10-24/25 waves: eMudhra egress, fleet breakers, Phonon, user RPD, webhooks, TTS bounds + trust/FinOps/voice set | 2–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, FinOps truth, push channels, local voice | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): **llama.cpp `/v1/realtime` + `POST /tts`**
(local realtime/speech passthrough becomes feasible — pairs with the
row-8 Realtime/WS demand trigger); **llama.cpp deferred tools +
`tool_reference` content parts** (adopt if clients send them); Portkey
Signals request-classifier mode (daari's decision_classifier is the
analog — compare once row 239 ships); Portkey claim-based JWT policies
(daari SSO/OIDC claim enforcement parity — file on demand); OpenRouter
S3/IAM observability destinations (spend-export-to-S3 analog, demand);
OpenAI `/agents/automations` passthrough; Prisma AIRS Agent Identity
Security; Claude Models on Google Cloud (IAM-auth egress — needs a Google
auth dependency, human sign-off); Anthropic hosted `/v1/skills` proxy
(local SEP-2640 shipped #1992 — proxy on demand); Claude Tag API beta
(non-goal); wider Responses `include` allowlist; Open Responses
WebSocket; Anthropic OTel export beta parity; Prometheus exemplars +
`gen_ai.agent.*`; LiteLLM 1.107+ watchables (ID-JAG / OAuth-delegate /
`agent_access_default_deny`); Portkey WIF upstream creds; SCIM +
multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter Private
Endpoints as an L6 slot recipe; certifi upstream drop of emSign roots;
llama.cpp `mtmd` capability helpers; Ollama LFM3/d1 Linux/Windows GA
(Apple-only in 0.40.12; llama.cpp covers Linux meanwhile — row 241);
MCP SEP-3415 Events extension + SEP-3392 extension lifecycle (active spec
PRs — revisit when merged).

Verified fine this run — don't re-audit: endpoint guardrail policies
already carry a `block_message` per endpoint (the gap is per-rule, row
237); MCP egress has per-server rpm/tpm (#1620 — timeout is the missing
knob, row 238); team labels exist on budget/rate-limit gauges (traffic
series are the gap, row 240); `daari_requests_total` splits tier +
modality; decisions ceilings and d1 catalog in-tree (#1989); SEP-2640
conformance + wave fence merged (#1992/#1993); sealed files/batches +
Helm key knobs merged (#1990/#1991).

---

## Path to enterprise-grade — next 5 milestones

1. **Match Portkey v2.31.0 where daari already owns the data** — signals
   in `daari_meta` + overrides (row 239), per-rule denial messages
   (row 237), per-server MCP timeouts (row 238), team traffic label
   (row 240).
2. **Finish the Ollama 0.40.12 ride-along** — LFM3 L3 recipe (row 233),
   doctor pulled-but-unused tip (row 234), `lfm3-audio` speech (row 235);
   point Linux operators at llama.cpp v0.8.0 meanwhile (row 241).
3. **Pay down the observability honesty tail** — decisions L0 scrape
   (row 236), reclaim/decrypt Prom (#1981), schema_ok copy (row 225),
   Phonon coercion counter (row 226), TTS/voices/skills P3s.
4. **Finish the tenancy set** — rows 62–67, then hot-reload (row 6).
5. **Demand-gated compliance and protocols** — row 8 (Realtime/WS gets
   closer now that llama.cpp serves `/v1/realtime` locally), row 7 parked.

---

## Changelog

- **2026-10-28 (match Portkey v2.31.0, ride llama.cpp v0.8.0)** — Whole
  10-27 board merged in a day (d1 catalog, at-rest Helm knobs + sealed
  files/batches, SEP-2640 conformance, wave fence). Corrected the stale
  "Portkey newest = v2.20.0" note: v2.31.0 (10-23) ships Signals beta,
  custom guardrail denial messages, per-MCP timeouts, Prom workspace
  label, claim-based JWT. llama.cpp v0.8.0 (first semver release) adds
  `/v1/realtime` + `/tts` and runs LFM3/d1 on Linux while Ollama 0.40.12
  GA stays Apple-only. Filed rows 237–241. LiteLLM 1.106.5 / OpenAI /
  Anthropic / Kong / vLLM flat; OpenRouter adds S3 IAM-role destinations
  (watch).

- **2026-10-27 + pm (finish what shipped; ride Ollama 0.40.12)** — Marked
  rows 217–224 Shipped; filed rows 227–231 (Helm at-rest knobs, seal
  files/batches, SEP-2640 conformance, wave fence, reclaim/decrypt Prom)
  and rows 232–236 (d1 catalog, LFM3 L3 recipe, doctor tip, lfm3-audio
  speech, decisions L0 Prom) after correcting the "rc1 is MLX-only" read.

- **2026-10-26 + pm (keep jobs alive, encrypt what we keep, mount the
  secrets; price Terra)** — Filed rows 217–226 across the am/pm siblings.

- **2026-10-25 → 08-28** — Condensed: prove-the-wave through Apache 2.0 and
  this PRD's creation.
