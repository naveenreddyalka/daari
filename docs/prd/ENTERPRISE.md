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

## Where daari stands (verified in-tree, 2026-09-09 pm)

**v1.4.0 is out and the morning refill shipped.** Phase routing (#380),
incremental stream guardrails (#381), key rotation (#383), and the audit hash
chain (#384) merged the same day they were filed. The only leftover from that
set is [#376](https://github.com/naveenreddyalka/daari/issues/376) (MCP
semantic tool search) — PR [#382](https://github.com/naveenreddyalka/daari/pull/382)
is open/`DIRTY` (needs `origin/main`). Eligible backlog was empty; this run
refills it.

Shipped surface (08-28→09-09): Apache 2.0, virtual keys + multi-window
budgets + teams + per-key RPM/TPM + global in-flight cap (#169) + key/SSO
expiry + `daari keys rotate`, SSO/OIDC, RBAC, hash-chained audit +
`list`/`export`/`verify`, retention, policy sync, fleet bootstrap, Redis
L0/L1 + Postgres ledger, Helm/Grafana, Prometheus + OTel, budget webhooks
(Redis-deduped), guardrails (chat + MCP, incremental stream mode), MCP
ingress/egress + pagination, session affinity, stall escalation, phase
routing, Responses API, embeddings, Ollama facade (`/api/generate`+embed),
OpenAI-compat local backends, OpenRouter `provider` object, agent prefix
L0/L1. Proof: 1588+ mocked tests; 320 rps L0 / 61 ms p95.

**Positioning:** Portkey changelog still quiet (PANW Prisma AIRS). Kong AI
Gateway quiet (2.0.3). LiteLLM's Auto-Router blog now sells
[pre-dispatch context-window escalation and modality routing](https://docs.litellm.ai/blog/auto-router-more-routing-configurations)
(09-01) plus `classification_mode: user_turn`; v1.97 adds
`scan_only_tool_results`. OpenRouter Batch API is documented and `cost_tier`
is GA on Auto. Routing customization stays metered behind LiteLLM's
`auto_router` license. daari's pitch: the same knobs, Apache 2.0, $0 local.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Context-window hop is reactive** — `_choose_initial_tier` does not compare `prompt_tokens_est` to the tier window; failover runs only after a local 400 (`failover.py`) | 4 | 3 | [LiteLLM context-window escalation](https://docs.litellm.ai/blog/auto-router-more-routing-configurations) (default on) | Token-count compare, no classifier; saves the failed local generate the IDE feels as TTFT | **Filed [#385](https://github.com/naveenreddyalka/daari/issues/385)** (P2) |
| 2 | **Streamed usage has no `cost`** — `usage_chunk()` emits tokens only; `X-Daari-Cost` cannot carry a post-stream figure | 3 | 2 | LiteLLM spend controls | `cost_usd()` already local (#278); local tiers are $0 | **Filed [#386](https://github.com/naveenreddyalka/daari/issues/386)** (P2) |
| 3 | **Chat tool results skip guardrails** — MCP `check_tool_result` exists; OpenAI `role=tool` / Anthropic `tool_result` reach the model unchecked | 3 | 2 | LiteLLM `scan_only_tool_results` (v1.97) | Same regex/PII engine; secrets in tool payloads never enter context or L0 | **Filed [#387](https://github.com/naveenreddyalka/daari/issues/387)** (P2) |
| 4 | **No in-body `cost_tier`** — OpenRouter Auto clients send `cost_tier` / `plugins.auto-router`; daari only reads `X-Daari-Tier-Cap` | 3 | 2 | OpenRouter Auto router | Map onto the existing L3–L6 cap; header still wins | **Filed [#388](https://github.com/naveenreddyalka/daari/issues/388)** (P2) |
| 5 | **Every tool turn re-profiles** — `build_prompt_profile` runs on continuations; `session_affinity` (default off) pins tier but still pays the profiler | 3 | 2 | LiteLLM `classification_mode: user_turn` | Message-list signal already in `session_affinity.is_tool_result` | **Filed [#389](https://github.com/naveenreddyalka/daari/issues/389)** (P2) |
| 6 | **MCP semantic tool search** — large aggregated catalogs vs small local models | 4 | 3 | LiteLLM `mcp_tool_search` | Local embeddings, $0 ranking | **In flight [#376](https://github.com/naveenreddyalka/daari/issues/376)** / [PR #382](https://github.com/naveenreddyalka/daari/pull/382) |
| 7 | **Batch API** — no `/v1/batches` | 4 | 4 | OpenRouter Batch API | Idle local tiers overnight at $0; MCP Tasks (#315) is the template | Watch — sketch when a daari client submits batches |
| 8 | **MCP agent identity** — [SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) still **draft** (re-checked 09-09 pm) | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` + key expiry are ready | Watch — file when SEP-1933 merges |
| 9 | **Gemini-native facade** — no `/v1beta` `generateContent` | 3 | 4 | Nobody self-hosted | Same dialect-facade as Ollama/Anthropic | Watch — file when a target client is confirmed |
| 10 | **A2A / admin UI / off-peak / `/v1/images`** | 2–3 | 2–4 | Kong / LiteLLM / OpenRouter | Unchanged; no new client demand this run | Watch / non-goal |
| 11 | **Ollama 0.34 facade** — still rc (ChatGPT Desktop, client tool search, compaction); facade uses `extra="ignore"` | 2 | 2 | Ollama upstream | #343 recipe | Watch — verify when 0.34.0 GAs |

Morning rows 1–5 from 09-09 (#374–#378) shipped except #376. Pruned from the
active table.

Open backlog after this run: #376 (PR in flight) plus
[#385](https://github.com/naveenreddyalka/daari/issues/385)–[#389](https://github.com/naveenreddyalka/daari/issues/389).

---

## Path to enterprise-grade — next 5 milestones

1. **Land #376** (merge [PR #382](https://github.com/naveenreddyalka/daari/pull/382)
   after it picks up `main`) so semantic tool search ships with the rest of
   the morning LiteLLM-parity set.
2. **Stop wasting the first local hop** ([#385](https://github.com/naveenreddyalka/daari/issues/385)):
   pre-dispatch context-window escalation is the routing feature LiteLLM just
   blogged; daari can do it with a token estimate.
3. **Spend + safety on the agent loop**
   ([#386](https://github.com/naveenreddyalka/daari/issues/386)/[#387](https://github.com/naveenreddyalka/daari/issues/387)):
   live `usage.cost` and tool-result guardrails are what Cursor-shaped
   clients already expect.
4. **Drop-in for OpenRouter bodies**
   ([#388](https://github.com/naveenreddyalka/daari/issues/388)/[#389](https://github.com/naveenreddyalka/daari/issues/389)):
   `cost_tier` + user-turn classification so a migrated client does not
   silently climb the ladder every tool turn.
5. **HITL leftovers:** set `AUTODEV_GH_TOKEN`; merge
   [#373](https://github.com/naveenreddyalka/daari/pull/373) (brew formula
   for v1.4.0). Batch API stays watch.

Standing HITL asks: `AUTODEV_GH_TOKEN` (user PAT, contents+PR); merge #373.

---

## Changelog

- **2026-09-09 pm** — Morning refill #374/#375/#377/#378 merged (PRs
  #380/#381/#383/#384). Eligible backlog empty except #376/`DIRTY` #382.
  Outward: LiteLLM context-window + modality blog; `user_turn` classifier
  mode; v1.97 `scan_only_tool_results`; OpenRouter Batch docs + GA
  `cost_tier`; SEP-1933 still draft; Ollama 0.34 still rc. Inward verified:
  `usage_chunk()` has no `cost`; tool-role messages skip guardrails; no
  `cost_tier` parse; context failover is post-error only. Filed
  [#385](https://github.com/naveenreddyalka/daari/issues/385)–[#389](https://github.com/naveenreddyalka/daari/issues/389)
  (all P2).
- **2026-09-09** — Park over, v1.4.0 released. Filed #374–#378.
- **2026-09-08** — Nine-PR park; filed #368 auto-drain + #369 alert dedupe.
- **2026-09-07** — Filed #355–#358 (pricing, affinity, stall, MCP pages).
- **2026-09-06** — #342–#345 (stall dedupe, ChatGPT Desktop, rollover, audit).
- **2026-09-03→09-02** — Labeler, expiry, retention, webhooks; Apache 2.0.
- **2026-08-28→09-01** (condensed) — Created this PRD; park class; PANW/Portkey.
