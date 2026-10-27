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

## Where daari stands (verified in-tree, 2026-10-27 pm)

**Loop velocity.** Morning's finish-the-wave five (rows 227–231 — Helm at-rest
`secretKeyRef`, seal files/batches, SEP-2640 conformance, wave fence,
reclaim/decrypt Prom) sit open alongside the leftover P3s (schema_ok copy,
Phonon coercion counter, voices console, skills CLI, TTS counters). The
encryption + skills finish set is still the merge spine.

**Outward.** Ollama **0.40.12-rc1** (published 2026-10-27) is **not**
MLX-runtime-only — it ships Liquid AI **LFM3** (1.7B text / vl / audio /
omni, 256K context) and **d1** decision models (`d1:2b`, `d1-omni`). That
lands squarely on daari's local Decisions + setup-models surface; the
built-in catalog still only knows `d3`/`d3:2b`… and Phonon for speech.
Elsewhere flat: LiteLLM **1.106.4**, OpenAI ends at 10-26 Terra (priced
in-tree), Anthropic 10-23 Claude Tag beta (non-goal), Portkey/Prisma AIRS
enterprise changelog newest entry **v2.20.0** (WIF for OpenAI/Anthropic —
still watch), Kong 2.2.0, vLLM 0.32.0.

**Inward theme: ride the Ollama cut.** Catalog the new d1 family so
`POST /v1/decisions` routes local without a config hammer; offer an
optional LFM3 L3 recipe next to Flint/Nemotron; doctor when the models
are pulled but unused; treat `lfm3-audio` as a first-class local speech
backend beside Phonon; and scrape decisions L0 cache hits so the local
judgment win is visible next to chat L0.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 232 | Catalog Liquid AI d1 / d1:2b / d1-omni in decisions built-in local models | 4 | 1 | Ollama + vLLM Semantic Router | Same `/v1/decisions` door, zero frontier hop | Filed [#1983](https://github.com/naveenreddyalka/daari/issues/1983) |
| 233 | Optional LFM3 L3 setup recipe (256K local agent tier) | 3 | 2 | Ollama `ollama run lfm3` | One `daari setup models` prompt, on-box | Filed [#1984](https://github.com/naveenreddyalka/daari/issues/1984) |
| 234 | Doctor tip when Ollama serves d1/lfm3 but catalog/recipes unused | 3 | 1 | — (ops honesty) | Point at the local win before L6 | Filed [#1985](https://github.com/naveenreddyalka/daari/issues/1985) |
| 235 | Recognize `lfm3-audio` as local ASR/TTS backend beside Phonon | 3 | 2 | Ollama speech / Phonon | 18-language local speech without cloud | Filed [#1986](https://github.com/naveenreddyalka/daari/issues/1986) |
| 236 | Prometheus + stats counter for decisions L0 cache hits | 2 | 1 | LiteLLM spend / cache tabs | Local judgment reuse is scrapeable | Filed [#1987](https://github.com/naveenreddyalka/daari/issues/1987) |
| 227 | Helm `secretKeyRef` knobs for the at-rest encryption key pair | 3 | 1 | LiteLLM raw env config | Customer key mounted from a Secret, never inlined | Filed [#1977](https://github.com/naveenreddyalka/daari/issues/1977) |
| 228 | Seal files + batches payload stores at rest (uploaded bytes, batch items) | 4 | 2 | OpenAI EKM | One `secret://` key seals every persisted payload on the box | Filed [#1978](https://github.com/naveenreddyalka/daari/issues/1978) |
| 229 | SEP-2640 conformance: advertise the skills extension, frontmatter + sha256 manifests, supporting files | 4 | 2 | MCP Python SDK built-in | On-box skills clients can actually discover, under local MCP grants | Filed [#1979](https://github.com/naveenreddyalka/daari/issues/1979) |
| 230 | Gateway-flow fence for the 10-26/27 wave (sealed-at-rest round-trip, Terra billing + surcharge, skills doors) | 3 | 2 | — (regression fence) | Hermetic in-process net that lets the loop merge daily | Filed [#1980](https://github.com/naveenreddyalka/daari/issues/1980) |
| 231 | Prom counters + alerts for orphan reclaim and at-rest decrypt failures | 2 | 2 | LiteLLM Errors tab | One page-worthy signal instead of scattered 500s | Filed [#1981](https://github.com/naveenreddyalka/daari/issues/1981) |
| 225 | `daari_schema_ok` HELP + Grafana copy cover Postgres skew | 2 | 1 | — (ops honesty) | Gauge already right; text lagged | Filed [#1966](https://github.com/naveenreddyalka/daari/issues/1966) |
| 226 | Prometheus counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform metrics | Local scrape next to the TTS path | Filed [#1967](https://github.com/naveenreddyalka/daari/issues/1967) |
| 217–224 | 10-26 waves: job lease/heartbeat + reclaim, at-rest encryption, Helm webhook knobs, wave fence, coercion warning, Terra day-one rates, grouped-report UI, SEP-2640 skills/list | 2–4 | 1–3 | OpenAI / LiteLLM / Bloomberg | HA jobs, EKM analog, push story, FinOps truth | Shipped |
| 206–216 | 10-24/25 wave | 2–4 | 1–2 | LiteLLM / Anthropic / OpenAI / Kong | Trust floor, FinOps truth, push channels, local voice | Shipped |
| 198–205 | eMudhra egress; fleet breakers; Phonon; compare 1.106.3; user RPD; webhooks; TTS bounds | 3–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, HA share, local voice, push channels | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
| 19–28 | compact_to_fit + MCP grant fail-closed + compare 1.104 | 2–4 | 1–2 | LiteLLM | Shipped | Shipped |
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): OpenAI `/agents/automations` passthrough
(demand-triggered); Prisma AIRS Agent Identity Security; **Claude Models on
Google Cloud (Anthropic managed)** as a frontier flavor (IAM-auth egress —
likely needs a Google auth dependency, human sign-off); Anthropic hosted
`/v1/skills` proxy (local SEP-2640 conformance first, row 229); Anthropic
**Claude Tag API** beta (10-23 — non-goal); wider Responses `include`
allowlist; Open Responses WebSocket; Anthropic OTel export beta parity;
Prometheus exemplars + `gen_ai.agent.*`; LiteLLM 1.107-rebuild watchables
(ID-JAG / OAuth-delegate / `agent_access_default_deny`); Portkey WIF
upstream creds (v2.20.0 shipped WIF for OpenAI/Anthropic — still demand);
SCIM + multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter
Private Endpoints as an L6 slot recipe; certifi upstream drop of emSign
roots; llama.cpp `mtmd` capability helpers; LFM3 Linux/Windows GA (rc1 is
Apple-hardware first).

Verified fine this run — don't re-audit: Terra rates/threshold match the
model page; orphan reclaim emits `responses.job_lease_reclaimed` (Prom gap
is row 231); at-rest rotation + doctor with #1958; Helm webhook knobs have
chart tests; lease behavior has `test_responses_job_lease.py`; Decisions GA
ceilings (`input_json`, 400 questions) and 12h prompt-cache write rates are
already in-tree; ultrafast allowlist stays sol/astra (Terra not advertised
upstream for ultrafast).

---

## Path to enterprise-grade — next 5 milestones

1. **Ride Ollama 0.40.12** — catalog d1 for local Decisions (row 232),
   optional LFM3 L3 recipe (row 233), doctor when pulled-but-unused
   (row 234), and `lfm3-audio` speech recognition (row 235).
2. **Finish the encryption story** — mount the key pair from a Kubernetes
   Secret (row 227) and seal files/batches payload stores (row 228).
3. **Make skills discoverable** — SEP-2640 capability advertisement +
   spec-shape manifests (row 229); fence the wave (row 230).
4. **Page on the new failure modes + judgment reuse** — reclaim/decrypt
   Prom (row 231), leftover P3 honesty (225–226), decisions L0 scrape
   (row 236).
5. **Finish the tenancy set** — rows 62–67, then hot-reload (row 6);
   demand-gated compliance (row 8) stays deferred.

---

## Changelog

- **2026-10-27 pm (ride Ollama 0.40.12 LFM3 + d1)** — Corrected the morning
  "0.40.12-rc1 is MLX-only" watch: the cut ships Liquid AI LFM3 (text/vl/
  audio/omni, 256K) and d1 decision models. LiteLLM 1.106.4 / Terra /
  Claude Tag / Kong 2.2.0 / vLLM 0.32.0 unchanged; Portkey enterprise
  changelog newest entry v2.20.0 (WIF — stay on watch). Filed rows
  232–236: d1 catalog, LFM3 L3 recipe, doctor tip, lfm3-audio speech,
  decisions L0 Prom. Condensed shipped bands 19–28 and 206–216 to keep
  the table under the line budget; encryption + SEP-2640 finish set
  (227–231) remains open.

- **2026-10-27 (finish what shipped yesterday)** — Marked rows 217–224
  Shipped; adopted sibling rows 222–226. Filed rows 227–231 (Helm at-rest
  knobs, seal files/batches, SEP-2640 conformance, wave fence,
  reclaim/decrypt Prom).

- **2026-10-26 + pm (keep jobs alive, encrypt what we keep, mount the
  secrets; price Terra)** — Filed rows 217–226 across the am/pm siblings.

- **2026-10-25 → 08-28** — Condensed: prove-the-wave through Apache 2.0 and
  this PRD's creation.
