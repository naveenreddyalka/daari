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

## Where daari stands (verified in-tree, 2026-09-13)

**Third consecutive same-day drain.** The 09-12 refill #441–#445 all merged the
same evening (PRs #447–#451): batch governance, the Files API, durable batches,
idle-yield drain, and `daari configure <client>`. Backlog and open PRs were both
empty at run start.

**Positioning:** outward moved this time — **Portkey shipped v2.22.0**, its
first substantive release since the PANW acquisition quiet period, headlined by
Anthropic-native `/v1/models` model discovery for Claude Code and client
`anthropic-beta` header passthrough. LiteLLM cut v1.102.0-rc.1 (stable still
v1.100.1); its notable entries — Responses-id authorization, complexity-routing
headers — map to gaps daari either shares or already covers (tier/cache/cost
headers shipped as #278/#319). Kong 2.0.3, Ollama 0.34.0, vLLM 0.29.0,
OpenRouter (08-19), and SEP-1933 are all unchanged.

**Inward theme of this run: stored-artifact tenancy.** The Batch/Files/Responses
surfaces persist artifacts, but every read path skips ownership: any virtual key
can list and download every other key's files (and delete them), read or cancel
any batch (inline results included), and fetch or chain any stored Response.
Execution is governed (#441); reads are not. That class plus the two Portkey
v2.22 parity items and file retention is this run's refill.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Batch + Files reads are cross-tenant** — list/get/cancel/delete/content ignore `auth_claims`; `FileStore` records no owner | 5 | 2 | OpenAI (project-scoped); LiteLLM authz fix [PR 39548](https://github.com/BerriAI/litellm/pull/39548) | `BatchGovernance.key_id` already snapshotted; one field + one check on a local store | **Filed [#452](https://github.com/naveenreddyalka/daari/issues/452)** (P1) |
| 2 | **Stored Responses readable/chainable across keys** — `GET /v1/responses/{id}` and `previous_response_id` skip owner checks | 4 | 2 | LiteLLM v1.102-rc.1 ([PR 39548](https://github.com/BerriAI/litellm/pull/39548)) | Store is one local SQLite file; owner column + WHERE clause | **Filed [#453](https://github.com/naveenreddyalka/daari/issues/453)** (P2) |
| 3 | **No Anthropic-native `/v1/models`** — Claude Code/Desktop can't discover models; `configure claude-desktop` verify hint hits the OpenAI shape | 4 | 2 | Portkey v2.22 headline | Cards come from daari's own tier catalog, no upstream aggregation | **Filed [#454](https://github.com/naveenreddyalka/daari/issues/454)** (P2) |
| 4 | **Client `anthropic-beta` dropped on L6** — betas (1M context, interleaved thinking) silently downgrade | 3 | 1 | Portkey v2.22 | One meta field + header merge on the L6 leg daari controls | **Filed [#455](https://github.com/naveenreddyalka/daari/issues/455)** (P2) |
| 5 | **Files store grows forever** — no `expires_after`, no retention sweep, no total-size cap; batch outputs accumulate on disk/PVC | 3 | 2 | OpenAI `expires_after` | daari owns the disk; retention is a local index sweep (#332 subsystem exists) | **Filed [#456](https://github.com/naveenreddyalka/daari/issues/456)** (P2) |
| 6 | **Percentile-TTFT routing** — LiteLLM still rc-only | 2 | 3 | LiteLLM `-rc` | Need latency histograms first | Watch |
| 7 | **MCP agent identity** — SEP-1933 still draft; new SEPs active (Skills 2640, audit-context 2817, server cards 2127) | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` ready | Watch |
| 8 | **Session-cumulative savings surfacing** — LiteLLM rc.1 shows routed model + session savings inside Claude Code/Codex | 2 | 2 | LiteLLM rc | Per-response `x-daari-response-cost-avoided` shipped; session rollup needs affinity store | Watch (file on stable release or client ask) |
| 9 | **SOC 2 / Gemini facade / A2A / admin UI / off-peak / `/v1/images` / WIF / streamed `usage.cost`** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: #441–#445 rows (all shipped 09-12, PRs #447–#451).

Open backlog after this run:
[#452](https://github.com/naveenreddyalka/daari/issues/452) (P1),
[#453](https://github.com/naveenreddyalka/daari/issues/453)–[#456](https://github.com/naveenreddyalka/daari/issues/456) (P2).

---

## Path to enterprise-grade — next 5 milestones

1. **Close the artifact-tenancy hole** ([#452](https://github.com/naveenreddyalka/daari/issues/452), [#453](https://github.com/naveenreddyalka/daari/issues/453)) — multi-tenant keys mean nothing if stored batches, files, and conversations leak across keys.
2. **Complete Anthropic-client onboarding** ([#454](https://github.com/naveenreddyalka/daari/issues/454)) — `daari configure claude-code` shipped; model discovery is the missing half of "point Claude Code at daari."
3. **Lossless Anthropic passthrough** ([#455](https://github.com/naveenreddyalka/daari/issues/455)) — client-requested betas must reach the provider or clients regress by switching to daari.
4. **Files lifecycle** ([#456](https://github.com/naveenreddyalka/daari/issues/456)) — overnight batch drain must not fill the operator's disk.
5. **Hold the routing-transparency lead** — tier/cache/cost headers already ship on every response; extend to session savings when LiteLLM's client-side savings display reaches stable (watch row 8).

---

## Changelog

- **2026-09-13** — Third same-day drain: #441–#445 merged 09-12 evening
  (PRs #447–#451); backlog empty. Outward: **Portkey v2.22.0** (first
  post-PANW substantive release — Anthropic-native `/v1/models` for Claude
  Code, `anthropic-beta` passthrough, Azure context/service-tier pricing);
  LiteLLM v1.102.0-rc.1 (Responses-id authz, complexity headers); Kong/
  Ollama/vLLM/OpenRouter/SEP-1933 unchanged. Inward: stored-artifact tenancy
  audit — batch/file/response read paths all skip ownership. Filed
  [#452](https://github.com/naveenreddyalka/daari/issues/452) (P1),
  [#453](https://github.com/naveenreddyalka/daari/issues/453)–[#456](https://github.com/naveenreddyalka/daari/issues/456)
  (P2).
- **2026-09-12** — Batch slice audit (governance bypass, `/v1/files`,
  durability, idle-yield) + `daari configure`. Filed #441–#445; all shipped
  same day.
- **2026-09-11 / 09-11 late / 09-11 pm** — Filed #418–#422 (harness-aware
  headline) and #430–#434 (Kong parity + Batch API); pm run no-delta.
- **2026-09-10** — Filed #409–#412; `AUTODEV_GH_TOKEN` set.
- **2026-09-09 evening / pm / day** — #397–#401, #385–#389, #374–#378.
- **2026-09-08→08-28** (condensed) — Park, labeler, Apache 2.0, this PRD.
