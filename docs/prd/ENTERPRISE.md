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

## Where daari stands (verified in-tree, 2026-10-27)

**Loop velocity.** Both 10-26 waves merged within a day: the morning five
(rows 217–221 — background-job lease/heartbeat + orphan reclaim, AES-GCM
at-rest encryption with key rotation, Helm webhook secret knobs, the
10-25/26 gateway fence, Phonon coercion warning) and the pm sibling's three
(rows 222–224 — day-one `gpt-6.1-terra` rates with the ≥272K surcharge,
web-ui grouped-report controls, SEP-2640 `skills/list` + `skill://`
resources). Only two sibling P3s (rows 225–226) and three loop P3s (voices
console, skills CLI, TTS counters) remain open.

**Outward.** Flat against what shipped overnight. OpenAI's changelog ends at
the 10-26 **GPT-6.1 Terra** launch — already priced in-tree ($1/$5, $0.05
cached, 272K threshold verified). LiteLLM floor stays **1.106.4**; Anthropic's
newest entry is the 10-23 **Claude Tag API** beta (Enterprise Slack org
settings — non-goal); Portkey/Prisma AIRS holds at v2.29.1; Ollama 0.40.11
GA (0.40.12-rc1 is MLX-runtime only); Kong 2.2.0; vLLM 0.32.0.

**Inward theme: finish what shipped yesterday.** The encryption key has
doctor coverage but zero Helm `secretKeyRef` plumbing — the exact anti-pattern
row 219 just eliminated for webhooks — and the files/batches stores (uploaded
file bytes, batch item payloads) stayed plaintext. The SEP-2640 surface is
invisible to conformant clients: `initialize` never advertises
`extensions["io.modelcontextprotocol/skills"]`, and entries lack the
frontmatter + sha256 manifest the final spec requires. Orphan reclaim and
`AtRestDecryptError` emit no Prometheus series, and the new wave has no
gateway-flow fence.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 227 | Helm `secretKeyRef` knobs for the at-rest encryption key pair | 3 | 1 | LiteLLM raw env config | Customer key mounted from a Secret, never inlined | Filed [#1977](https://github.com/naveenreddyalka/daari/issues/1977) |
| 228 | Seal files + batches payload stores at rest (uploaded bytes, batch items) | 4 | 2 | OpenAI EKM | One `secret://` key seals every persisted payload on the box | Filed [#1978](https://github.com/naveenreddyalka/daari/issues/1978) |
| 229 | SEP-2640 conformance: advertise the skills extension, frontmatter + sha256 manifests, supporting files | 4 | 2 | MCP Python SDK built-in | On-box skills clients can actually discover, under local MCP grants | Filed [#1979](https://github.com/naveenreddyalka/daari/issues/1979) |
| 230 | Gateway-flow fence for the 10-26/27 wave (sealed-at-rest round-trip, Terra billing + surcharge, skills doors) | 3 | 2 | — (regression fence) | Hermetic in-process net that lets the loop merge daily | Filed [#1980](https://github.com/naveenreddyalka/daari/issues/1980) |
| 231 | Prom counters + alerts for orphan reclaim and at-rest decrypt failures | 2 | 2 | LiteLLM Errors tab | One page-worthy signal instead of scattered 500s | Filed [#1981](https://github.com/naveenreddyalka/daari/issues/1981) |
| 225 | `daari_schema_ok` HELP + Grafana copy cover Postgres skew | 2 | 1 | — (ops honesty) | Gauge already right; text lagged | Filed [#1966](https://github.com/naveenreddyalka/daari/issues/1966) |
| 226 | Prometheus counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform metrics | Local scrape next to the TTS path | Filed [#1967](https://github.com/naveenreddyalka/daari/issues/1967) |
| 217–224 | 10-26 waves: job lease/heartbeat + reclaim, at-rest encryption, Helm webhook knobs, wave fence, coercion warning, Terra day-one rates, grouped-report UI, SEP-2640 skills/list | 2–4 | 1–3 | OpenAI / LiteLLM / Bloomberg | HA jobs, EKM analog, push story, FinOps truth | Shipped |
| 206–216 | 10-24/25 wave: strip visibility, image trust-store scrub, wave coverage, grouped reports, breaker observability, user_id fences, webhook doctor + panels, Phonon tags, AAIF Skills, TTS benchmark | 2–4 | 1–2 | LiteLLM / Anthropic / OpenAI / Kong | Trust floor, FinOps truth, push channels, local voice | Shipped |
| 198–205 | eMudhra egress distrust; fleet breakers; Phonon voices; compare 1.106.3; user RPD; webhook delivery + ingest hardening; TTS bounds | 3–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, HA share, local voice, push channels | Shipped |
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

Watch rows (do not file yet): OpenAI `/agents/automations` passthrough
(demand-triggered); Prisma AIRS Agent Identity Security; **Claude Models on
Google Cloud (Anthropic managed)** as a frontier flavor (IAM-auth egress —
likely needs a Google auth dependency, human sign-off); Anthropic hosted
`/v1/skills` proxy (local SEP-2640 conformance first, row 229); Anthropic
**Claude Tag API** beta (10-23, Enterprise Slack org settings — non-goal
unless gateways get asked to proxy it); wider Responses `include` allowlist
(`_SUPPORTED_INCLUDES` is still only `reasoning.encrypted_content`); Open
Responses WebSocket; Anthropic OTel export beta parity; Prometheus exemplars
+ `gen_ai.agent.*`; LiteLLM 1.107-rebuild watchables (ID-JAG / OAuth-delegate
/ `agent_access_default_deny`); Portkey WIF upstream creds; SCIM +
multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter Private
Endpoints as an L6 slot recipe; certifi upstream drop of emSign roots;
llama.cpp `mtmd` capability helpers and Ollama 0.40.12-rc1 (both
runtime-only, no router surface yet).

Verified fine this run — don't re-audit: a whole band of old watch rows is
now in-tree and dead: web-ui events filters (team/key/kind/since/until +
pagination), spend-export team/until/model/speed controls in the console,
enforcement inventory + cache-invalidate form in the web-ui, `daari migrate
--downgrade`, `/ready` carries `schema_ok` (PG skew included), audit-list
team filter (#1711), Grafana gzip + cache-write-TTL panels, W3C
`traceresponse` reply header (#1682), `daari configure` covers all nine
registry clients. On the new wave: Terra rates/threshold match the model
page; orphan reclaim emits the `responses.job_lease_reclaimed` gateway event
(gap is Prometheus only, row 231); at-rest rotation (`previous_key`) and the
doctor check shipped with #1958; Helm webhook knobs have chart tests
(`test_helm_webhooks.py`); lease behavior has its own integration module
(`test_responses_job_lease.py`).

---

## Path to enterprise-grade — next 5 milestones

1. **Finish the encryption story** — mount the key pair from a Kubernetes
   Secret (row 227) and seal the last plaintext payload stores: uploaded
   file bytes and batch items (row 228). One customer-held key, every
   persisted payload sealed.
2. **Make skills discoverable** — advertise the SEP-2640 extension and ship
   spec-shape manifests so Claude Code and other conformant clients can
   actually find on-box skills (row 229).
3. **Fence the wave, page on the new failure modes** — gateway-flow coverage
   for at-rest, Terra billing, and the skills doors (row 230); counters +
   alerts for orphan reclaim and decrypt failures (rows 231, 225, 226).
4. **Finish the tenancy set** — end-user inventory/overrides, guardrail
   profiles, paged rollups and console rendering (rows 62–67), then
   hot-reload (row 6).
5. **Demand-gated compliance** — SCIM, WIF depth, A2A, Realtime/WS, FIPS,
   HIPAA BAA, Open Responses WS stay deferred until a buyer asks.

---

## Changelog

- **2026-10-27 (finish what shipped yesterday)** — Marked rows 217–224
  Shipped (both 10-26 waves merged overnight); adopted the pm sibling's
  rows 222–226 after its PRD PR #1968 pruned the pinned rows and failed the
  pin test. Outward flat: LiteLLM 1.106.4 floor holds, OpenAI ends at the
  10-26 Terra launch (already priced in-tree), Anthropic ends at the 10-23
  Claude Tag beta (non-goal), Portkey v2.29.1, Ollama 0.40.11
  (0.40.12-rc1 MLX-only). Filed rows 227–231: Helm knobs for the at-rest
  key pair, sealing files/batches stores, SEP-2640 conformance (no
  capability advertisement today — conformant clients never call
  `skills/list`), the 10-26/27 wave fence, and reclaim/decrypt-failure
  observability. Pruned a band of dead watch rows now verified in-tree
  (console filters, `--downgrade`, `schema_ok` on `/ready`, gzip/TTL
  panels, `traceresponse`).

- **2026-10-26 + pm (keep jobs alive, encrypt what we keep, mount the
  secrets; price Terra)** — Filed rows 217–221 (background-job lease,
  at-rest encryption, Helm webhook secrets, wave fence, coercion honesty);
  the pm sibling filed rows 222–226 (Terra day-one rates, grouped-report
  UI, SEP-2640 skills/list, schema_ok copy, coercion counter). Verified
  shipped day-2: grouped-report HTTP route, user_rpd admin visibility,
  console breaker inventory/reset, complete configure recipes.

- **2026-10-25 (prove the wave, report on it, ship a clean image)** — Marked
  rows 198–205 and the console/PG pair Shipped. Outward: LiteLLM 1.106.4
  image hygiene; Ollama 0.40.11 GA (parity held); OpenAI EKM + UK residency
  + `/agents/automations`; Prisma AIRS Agent Identity Security. Filed rows
  207–211; adopted the pm sibling's rows 212–216 after its PRD branch
  pruned the pinned rows and failed the pin test.

- **2026-10-24 → 08-28** — Condensed: trust floors, HA share, local voice,
  push channels; bill-what-was-served + GA parity; finish-the-truths,
  console and day-2 packaging; breaker truth, invoice-true cache billing,
  user profiles; LiteLLM compromise + Anthropic API-version footgun;
  finish-the-knobs; decisions depth; `resultType`/egress waves; Apache 2.0;
  this PRD's creation.
