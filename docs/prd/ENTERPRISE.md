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

## Where daari stands (verified in-tree, 2026-10-23 pm)

**Loop velocity.** Morning PRD wave (served-tier billing, Decisions GA,
d3/Flint, streamed TTS, wave observability) is filed and on `main` via the
merged ENTERPRISE refresh; both 10-22 implementation waves remain merged.
Eligible picker queue still holds the morning five plus fleet cancel /
enforcement webhook ingest and the 10-10 tenancy/console set (`agent:working`).

**Outward.** Ollama **0.40.10** GA (same day): NVIDIA **Nemotron 3.5 Bolt
E4B** VLM (`nemotron-3.5-bolt:e4b`, 128K, DFlash). Anthropic migration
`2026-10-21` clarifies two more 400s beyond sampling — assistant `document`
blocks and non-empty user/search_result `citations`. LiteLLM PyPI floor
still **1.106.2** (no clean 1.108 publish; 1.107 remains compromised).
eMudhra/emSign: browsers + certifi 2026.10.19+ already acted; daari watches
buyer-pinned `TLS_CA` only. Kong AI Gateway 2.2 / OpenRouter private
endpoints / vLLM 0.32.0 / Portkey flat vs morning scan.

**Inward theme: finish the API-version footgun, push completions, console
the day-2 knobs, gate PG like SQLite.** Sampling strip shipped; document/
citations still pass through to a 400. Background Responses reach terminal
state without a signed completion webhook. Enforcement inventory + cache
invalidate exist on HTTP/CLI but not in `packages/web-ui`. `/ready`
`schema_ok` is SQLite-honest; Postgres is connect-only and migrate has no
downgrade.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 198 | Version-safe strip: assistant `document` + user `citations` under Anthropic `2026-10-21` | 4 | 2 | Anthropic migration guide | Same soft_warning path as sampling strip | Filed [#1891](https://github.com/naveenreddyalka/daari/issues/1891) |
| 199 | Signed completion webhooks for background Responses jobs | 4 | 3 | OpenAI background webhooks | Reuse signed-deliver; notify from owning pod | Filed [#1892](https://github.com/naveenreddyalka/daari/issues/1892) |
| 200 | Ollama 0.40.10 Nemotron 3.5 Bolt E4B local VLM recipe | 3 | 1 | Ollama / NVIDIA | Zero-config $0 multimodal tier on primary runtime | Filed [#1893](https://github.com/naveenreddyalka/daari/issues/1893) |
| 201 | Web-ui: enforcement inventory panel + cache-invalidate admin form | 3 | 2 | LiteLLM admin UI | HTTP/CLI exist; console finishes day-2 | Filed [#1894](https://github.com/naveenreddyalka/daari/issues/1894) |
| 202 | Postgres `schema_ok` skew gate on `/ready` + `migrate --downgrade` | 3 | 2 | Cloud gateway migrate tooling | SQLite already gates; PG buyers need parity | Filed [#1895](https://github.com/naveenreddyalka/daari/issues/1895) |
| 193 | Bill served `service_tier` on spend ledger + stream cost headers after degrade | 4 | 2 | OpenAI invoice / LiteLLM | Degrade and ledger live in one process | Open ([#1885](https://github.com/naveenreddyalka/daari/issues/1885)) |
| 194 | OpenAI Decisions GA parity: `input_json`, per-question images, 400-question cap, cached-input billing | 4 | 2 | OpenAI (GA 10-22) | One GA shape, served locally at $0 or forwarded | Open ([#1886](https://github.com/naveenreddyalka/daari/issues/1886)) |
| 195 | Built-in d3 local decision models + Flint Linux/Windows recipe (Ollama 0.40.9) | 3 | 1 | Ollama / vLLM Semantic Router | Zero-config $0 judge tier | Open ([#1887](https://github.com/naveenreddyalka/daari/issues/1887)) |
| 196 | Stream `/v1/audio/speech` relay + Ollama Phonon local TTS recipe | 3 | 2 | OpenAI TTS / Ollama 0.40.9 | Local voice behind daari auth/budgets/audit | Open ([#1888](https://github.com/naveenreddyalka/daari/issues/1888)) |
| 197 | Panels + alert rules for `service_tier_degraded`, `anthropic_sampling_stripped`, enforced-profiles gauge | 3 | 2 | Datadog / Grafana Cloud packs | Series already on `/metrics` | Open ([#1889](https://github.com/naveenreddyalka/daari/issues/1889)) |
| 191 | Fleet-coordinate Responses background job cancel | 4 | 3 | OpenAI background cancel | Redis/lease cancel stops the owning pod | Open ([#1874](https://github.com/naveenreddyalka/daari/issues/1874)) |
| 192 | Ingest Anthropic org enforcement webhooks | 4 | 3 | Anthropic Admin API | Push joins local tenant map + audit | Open ([#1875](https://github.com/naveenreddyalka/daari/issues/1875)) |
| 183–190 | 10-22 waves: streamed cache-write TTL billing; enforcement sync; service-tier degrade; Redis breaker; sampling-strip telemetry; console export/reset; gzip + TTL panels; vLLM floor doc | 3–4 | 1–3 | OpenAI / Anthropic / Kong / LiteLLM | Invoice, blast-radius, HA, day-2 truths | Shipped |
| 136–182 | 10-18 → 10-21 waves (protocol, egress, FinOps, judge ops) | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Local-first parity | Shipped |
| 62–67 | End-user inventory; guardrail profiles; web-ui keys/teams/`report.users`; bound report rollups; multi_agent nested `model` | 4–5 | 2–3 | OpenRouter / LiteLLM / Portkey | Ledger + console already partial | Open (`agent:working`) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
| 19–28 | compact_to_fit ownership/doctor/hermetic/`daari_meta`/MCP grant fail-closed + Prom; compare-litellm refresh | 2–4 | 1–2 | LiteLLM | — | Shipped |

Watch rows (do not file yet): fleet-share remaining circuit breakers —
frontier/local pool/MCP egress still process-local (systemone Redis pattern
shipped; file once one more shared breaker lands without flake); LiteLLM
clean post-compromise rebuild (PyPI still 1.106.2 — revisit ID-JAG /
`agent_access_default_deny` when a signed 1.108+ appears); Portkey WIF
upstream creds (buyer ask); per-user RPD; SCIM + multi-issuer SSO;
Prometheus exemplars + `gen_ai.agent.*`; Kong Skills/A2A passthrough
demand; eMudhra buyer-pinned `TLS_CA` only (certifi ≥2026.10.19 already
safe).

Verified fine this run — don't re-audit: morning rows 193–197 still open
(correctly); sampling strip limited to `temperature`/`top_p`/`top_k` (gap is
document/citations = row 198); systemone Redis breaker fails open with
`/ready`/stats/reset; enforcement sync poll + state + signed outbound + Prom
+ doctor + HTTP/CLI (ingest = 192; console surface = 201); background
Responses terminal persistence without completion push (row 199); SQLite
`schema_ok` only (row 202); Flint recipe exists — Bolt E4B does not (row
200); Decisions GA fields / served-tier spend / streamed TTS still morning
queue.

---

## Path to enterprise-grade — next 5 milestones

1. **Finish Anthropic `2026-10-21`** — document/citations strip (row 198)
   beside the shipped sampling strip so L6 never 400s after local work.
2. **Background Responses push** — signed completion webhooks (row 199) next
   to fleet cancel (191).
3. **Local multimodal recipe** — Nemotron Bolt E4B on Ollama 0.40.10 (row
   200), stacking on d3/Flint/Phonon morning filings.
4. **Console the day-2 knobs** — enforcement inventory + cache invalidate in
   web-ui (row 201).
5. **PG migrate honesty** — `schema_ok` skew on `/ready` + `migrate
   --downgrade` (row 202), then drain HA/tenancy (191–192, 62–67).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-23 pm (API-version footgun, completion push, console, PG gate)** —
  Outward: Ollama 0.40.10 GA (Nemotron 3.5 Bolt E4B); Anthropic
  document/citations 400s under `2026-10-21`; LiteLLM PyPI still 1.106.2.
  Filed rows 198–202: version-safe content strip, Responses completion
  webhooks, Bolt E4B recipe, web-ui enforcement + cache invalidate, Postgres
  `schema_ok` + migrate downgrade. Morning rows 193–197 remain Open.

- **2026-10-23 (bill what was served, speak what went GA)** — Marked rows
  183–190 Shipped. Outward: Ollama 0.40.9; Decisions GA; eMudhra distrust;
  semantic-router 1.0/1.1. Filed rows 193–197.

- **2026-10-22 + pm (finish the truths; console and day-2 packaging)** —
  Marked rows 171–182 Shipped. Filed rows 183–192.

- **2026-10-21 + pm → 08-28** — Condensed: breaker truth; invoice-true cache
  billing; user profiles; LiteLLM compromise; decisions/fast-mode/`resultType`
  waves; lifecycle/tenancy/DR; Apache 2.0; this PRD's creation.
