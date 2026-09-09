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

## Where daari stands (verified in-tree, 2026-09-09 evening)

**The afternoon refill shipped in hours.** #376 / #385–#387 / #389 are on
`main` (PRs #382 / #391 / #392 / #393 / #395). [#388](https://github.com/naveenreddyalka/daari/issues/388)
(`cost_tier`) is the leftover — [PR #394](https://github.com/naveenreddyalka/daari/pull/394)
open. Eligible backlog emptied again; this run refills it.

Shipped surface now also includes: MCP semantic tool search, pre-dispatch
context-window escalation, streamed `usage.cost`, chat tool-result
guardrails, user-turn profile reuse. Proof: 1619+ mocked tests.

**Positioning:** LiteLLM is still selling the 09-01 Auto-Router blog
(context-window + **modality** + `user_turn`). daari matched four of those
five knobs today; images nested in **tool results** are the remaining
modality hole. Ollama **0.34 still rc3** (re-checked 09-09 eve). SEP-1933
still draft. Portkey / Kong quiet.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Tool-result images skip vision** — `required_capabilities` only sees `Message.images`; Anthropic `tool_result` uses `content_to_text` and drops image blocks | 4 | 2 | [LiteLLM `modality_routing`](https://docs.litellm.ai/blog/auto-router-more-routing-configurations) | Same #164 catalog; escalate to local vision L4/L5 instead of a provider 400 | **Filed [#397](https://github.com/naveenreddyalka/daari/issues/397)** (P2) |
| 2 | **`json_schema` dropped** — `SamplingParams` only honors `response_format.type == json_object` | 3 | 2 | OpenAI structured outputs | Ollama already takes `format` as a schema object | **Filed [#398](https://github.com/naveenreddyalka/daari/issues/398)** (P2) |
| 3 | **Stream usage has no cached tokens** — #386 added `cost`; OpenAI UIs also read `prompt_tokens_details.cached_tokens` | 3 | 2 | LiteLLM / OpenAI prefix cache | `daari_meta.cached_tokens` already parsed on L6; L0/L1 are fully cached | **Filed [#399](https://github.com/naveenreddyalka/daari/issues/399)** (P2) |
| 4 | **`/v1/models` hides context windows** — #385 table is internal-only | 3 | 2 | OpenRouter / Ollama `/api/tags` | Clients stop guessing 4k and trimming pastes L4 would take | **Filed [#400](https://github.com/naveenreddyalka/daari/issues/400)** (P2) |
| 5 | **`long_context` still uses 24k chars** — disagrees with `routing.context_windows` × 0.95 | 3 | 2 | (daari self-inflicted) | One table, one hop | **Filed [#401](https://github.com/naveenreddyalka/daari/issues/401)** (P2) |
| 6 | **In-body `cost_tier`** | 3 | 2 | OpenRouter Auto | Header still wins | **In flight [#388](https://github.com/naveenreddyalka/daari/issues/388)** / [PR #394](https://github.com/naveenreddyalka/daari/pull/394) |
| 7 | **Batch API** — no `/v1/batches` | 4 | 4 | OpenRouter Batch API | Idle local tiers overnight; MCP Tasks (#315) template | Watch |
| 8 | **MCP agent identity** — [SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) still **draft** | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` + key expiry ready | Watch |
| 9 | **Gemini facade / A2A / admin UI / off-peak / `/v1/images`** | 2–3 | 2–4 | Kong / LiteLLM / OpenRouter | No new client demand this run | Watch / non-goal |
| 10 | **Ollama 0.34 facade** — still **rc3** (ChatGPT Desktop, tool search, compaction) | 2 | 2 | Ollama upstream | #343 recipe | Watch — verify when 0.34.0 GAs |

Afternoon rows #385–#387 / #389 and #376 shipped. Pruned from the active table.

Open backlog after this run: #388 (PR in flight) plus
[#397](https://github.com/naveenreddyalka/daari/issues/397)–[#401](https://github.com/naveenreddyalka/daari/issues/401).

---

## Path to enterprise-grade — next 5 milestones

1. **Land #388** (merge [PR #394](https://github.com/naveenreddyalka/daari/pull/394)
   after it picks up `main`) so OpenRouter bodies map `cost_tier`.
2. **See what agents see** ([#397](https://github.com/naveenreddyalka/daari/issues/397)):
   tool-result screenshots are the last LiteLLM modality gap.
3. **Structured outputs + honest catalog**
   ([#398](https://github.com/naveenreddyalka/daari/issues/398)/[#400](https://github.com/naveenreddyalka/daari/issues/400)/[#401](https://github.com/naveenreddyalka/daari/issues/401)):
   json_schema through, windows advertised, one long-context rule.
4. **Finish live spend** ([#399](https://github.com/naveenreddyalka/daari/issues/399)):
   cached tokens next to `usage.cost`.
5. **HITL leftovers:** `AUTODEV_GH_TOKEN`; merge
   [#373](https://github.com/naveenreddyalka/daari/pull/373) (brew v1.4.0).
   Batch API stays watch.

Standing HITL asks: `AUTODEV_GH_TOKEN`; merge #373.

---

## Changelog

- **2026-09-09 evening** — Afternoon refill shipped (#376/#385/#386/#387/#389).
  Outward: LiteLLM modality routing still the advertised hole; Ollama 0.34
  rc3; SEP-1933 draft. Inward: Anthropic `tool_result` drops images;
  `json_schema` ignored; stream usage has cost but no cached tokens;
  `/v1/models` omits `context_windows`; `long_context` still 24k chars.
  Filed [#397](https://github.com/naveenreddyalka/daari/issues/397)–[#401](https://github.com/naveenreddyalka/daari/issues/401)
  (all P2).
- **2026-09-09 pm** — Filed #385–#389.
- **2026-09-09** — Park over, v1.4.0 released. Filed #374–#378.
- **2026-09-08** — Nine-PR park; filed #368 / #369.
- **2026-09-07→08-28** (condensed) — Affinity, stall, MCP pages, labeler,
  Apache 2.0, this PRD.
