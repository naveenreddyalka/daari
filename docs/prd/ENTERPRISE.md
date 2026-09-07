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

## Where daari stands (verified in-tree, 2026-09-07)

**The loop is fully parked on one human action.** All five open PRs —
[#340](https://github.com/naveenreddyalka/daari/pull/340) (v1.4.0 prep),
[#347](https://github.com/naveenreddyalka/daari/pull/347) (stall re-pick dedupe),
[#348](https://github.com/naveenreddyalka/daari/pull/348) (ChatGPT Desktop facade),
[#349](https://github.com/naveenreddyalka/daari/pull/349) (budget rollover),
[#350](https://github.com/naveenreddyalka/daari/pull/350) (audit export) —
are bot-authored and held on `action_required`: CI never starts, auto-merge
waits forever. The 09-06 refill (#342–#345) was picked up and implemented
within hours; every result is now queued behind the same Actions approval
policy. **Loop hygiene is otherwise healthy**: the stall watcher classified all
five as `awaiting-approval`, filed one regression issue per PR
(#341, #351–#354) with exactly one comment each — no re-pick spam (the
permanent fix is itself parked in #347).

Human unpark, in order: approve the held workflow runs for PRs #340 and
#347–#350 (or relax the Actions approval policy for repo-workflow bot PRs —
this is now the **fourth** `action_required` park), let auto-merge drain,
close stall issues #341/#351–#354, then tag v1.4.0.

Longer-standing surface (see 08-28→09-06 scans): Apache 2.0
([ADR-0016](../adr/0016-apache-2-relicense.md)), virtual keys + multi-window
budgets + teams + per-key RPM/TPM + key/SSO expiry, SSO/OIDC + IdP-minted keys,
RBAC, append-only audit, retention/prune, policy sync, fleet bootstrap,
Redis L0/L1 + Postgres ledger/traces, Helm + Grafana, Prometheus + OTel GenAI,
budget headers + threshold webhooks, guardrails + PII scrub (chat + MCP), MCP
ingress (2026-07-28, Tasks) + egress governance with per-key/team tool
governance, `secret://` refs incl. OAuth client-credentials, Responses API,
`/v1/embeddings`, Ollama facade, OpenAI-compat local backends
(vLLM/llama.cpp/LM Studio), OpenRouter `provider` object, per-model +
cached-input pricing, context-length failover + compression, circuit breakers,
signed images + SBOM, shadow evals. Proof: 1141+ mocked tests; published load
(320 rps L0 / 61 ms p95), vs-LiteLLM, cost-of-pass pages.

**Positioning:** Portkey is now the PANW Prisma AIRS AI Gateway (changelog
quiet since April; enterprise still v2.20). **New this week:** LiteLLM
v1.101-rc.1 [meters auto-router customization behind an `auto_router`
enterprise license](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1)
— beyond one heuristic router, custom tier definitions/classifier prompts
refuse to start unlicensed. daari's counter-pitch sharpens: routing *is* the
Apache 2.0 core — cache → rules → local tiers → frontier, all free,
run-it-yourself, tokens never leave the building.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Everything parked on Actions approval** — 5 done PRs (v1.4.0 prep + the whole 09-06 refill) held on `action_required`; fourth occurrence; nothing merges until a human clicks | 5 | 0 | n/a (policy) | n/a — human-only | HITL: approve held runs for [#340](https://github.com/naveenreddyalka/daari/pull/340), [#347](https://github.com/naveenreddyalka/daari/pull/347)–[#350](https://github.com/naveenreddyalka/daari/pull/350) or relax bot-PR approval policy; then tag v1.4.0 |
| 2 | **Shipped pricing table is two years stale** — tops out at `gpt-4o`/`claude-3-5`; Claude Fable 5.1 (09-01) and GPT-6 Astra (09-03) bill at the flat fallback rate, so budgets/402s, cost headers, ledger, and savings numbers are wrong out of the box | 4 | 1 | [LiteLLM 411 day-0 models in v1.101-rc.1](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) | On-box FinOps is the pitch; accuracy needs no vendor sync — but only if shipped defaults are current | [#355](https://github.com/naveenreddyalka/daari/issues/355) (P1) |
| 3 | **No session affinity** — every request re-routes; agent loops can switch models mid-task, discarding local KV/prompt cache and changing behavior mid-plan | 4 | 3 | [LiteLLM `user_turn` + session pinning](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) (85% fewer classifier calls, zero mid-loop switches — behind enterprise license) | Stickiness preserves Ollama/llama.cpp server-side prompt cache → TTFT wins on every continuation turn, at $0; pin store is local | [#356](https://github.com/naveenreddyalka/daari/issues/356) (P2) |
| 4 | **No stall escalation** — a small local model repeating the same tool call burns wall-clock forever; confidence heuristics only look at single responses | 3 | 2 | [LiteLLM `stall_escalation`](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) (3 repeats / last 6 tool calls) | Stateless — evidence is in the request history; converts a wedged $0 loop into a completed task at minimal frontier spend | [#357](https://github.com/naveenreddyalka/daari/issues/357) (P2) |
| 5 | **MCP egress reads one page of `tools/list`** — no `nextCursor` follow; multi-page upstream catalogs are silently truncated, so tool governance evaluates an incomplete catalog | 3 | 2 | LiteLLM fixed the same in v1.101-rc.1 (PR #39172) | Governed egress is the MCP pitch; completeness of the governed catalog is the product | [#358](https://github.com/naveenreddyalka/daari/issues/358) (P2) |
| 6 | **Batch API** — no `/v1/batches`; agents and eval pipelines increasingly submit batch jobs | 4 | 4 | OpenRouter Batch API (beta); LiteLLM e2e batch billing | Drain batches through idle local tiers overnight at $0 — no cloud gateway can copy it. MCP Tasks store (#315) is the template | File when a daari-served client sends batches; sketch first |
| 7 | **MCP semantic tool search** — big tool catalogs drown agent context; no server-side relevance ranking | 3 | 3 | [LiteLLM `mcp_tool_search`](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) (embedding-ranked, keyword fallback) | daari has `/v1/embeddings` + local embed models → $0 ranking on-box | Watch — file after #358 lands and a daari-served client hits a large catalog |
| 8 | **Overload admission control** — per-key RPM/TPM 429s exist, but no in-flight cap / fast 503 when local backends saturate | 3 | 3 | [LiteLLM `max_in_flight_requests_per_worker`](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) | Local GPUs saturate long before the gateway; failing fast beats queueing into timeout | Watch — file when a load report shows queue collapse, or with the next HA milestone |
| 9 | **MCP agent identity** — [WIF SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) + DPoP SEP-1932 both still **draft** (checked 09-07); conformance scenarios in progress | 3 | 3 | MCP Tier-1 SDKs; LiteLLM MCP session RFC 7662 | Workload JWTs (K8s/SPIFFE) as inbound auth fit fleets; `secret://oauth` (#329) + key expiry (#337) are the groundwork | Watch — file when SEP-1933 merges or a fleet asks |
| 10 | **Gemini-native facade** — no `/v1beta` `generateContent`; Gemini CLI can't point at daari | 3 | 4 | Nobody self-hosted | Same dialect-facade trick as Ollama/Anthropic | Watch — file when a target client is confirmed |
| 11 | **A2A gateway** — no Agent2Agent ingress/egress governance | 3 | 4 | Kong Agent Gateway | Local agents delegating over A2A get routing/cache/policy without a cloud hop | Watch — revisit when a daari-served client speaks A2A |
| 12 | **Admin console** — web dashboard read-only; key/team/budget management is CLI-only | 3 | 4 | LiteLLM admin UI | CLI-first fits operators; a UI matters at org rollout scale | Watch — wait for operator demand |
| 13 | **Off-peak pricing windows** — some providers discount by time window; daari prices flat per model | 2 | 2 | [LiteLLM `off_peak_pricing`](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) | Local math at cost time; pairs with #344 rollover | Watch — file when a provider daari routes to publishes off-peak rates |
| 14 | **Per-request `cost_tier` body param** — OpenRouter Auto router takes it in-body; daari has `X-Daari-Tier-Cap` header + profiles | 2 | 2 | OpenRouter Auto router | Header + `.daari.yaml` cover most cases | Watch — file if a client can't set headers |
| 15 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API (GA'd Responses this week) | Local diffusion is a different product | Non-goal for now |

Open backlog after this run:
[#355](https://github.com/naveenreddyalka/daari/issues/355) (pricing refresh, P1),
[#356](https://github.com/naveenreddyalka/daari/issues/356) (session affinity, P2),
[#357](https://github.com/naveenreddyalka/daari/issues/357) (stall escalation, P2),
[#358](https://github.com/naveenreddyalka/daari/issues/358) (MCP pagination, P2) —
all auto-labeled at filing. Human-gated: #334/#341/#351–#354 (all resolve with
the run approvals above). #342–#345 have open PRs (#347–#350) awaiting the same.

---

## Path to enterprise-grade — next 5 milestones

1. **Unpark the pipeline and ship v1.4.0** (row 1, human-only): approving five
   held runs merges the entire 09-06 refill plus release prep; then tag. This
   single click is worth more than any issue this run can file. Strongly
   consider relaxing the Actions approval policy for repo-workflow bot PRs —
   four parks in ten days is a structural tax on the loop.
2. **Make the FinOps numbers true** (row 2, #355): budgets, 402s, cost headers,
   and savings claims must price the September 2026 frontier lineup correctly.
   Cheapest highest-leverage fix in the table.
3. **Win the agent-loop routing race** (rows 3–4, #356/#357): LiteLLM just put
   session pinning and stall escalation behind an enterprise license. Shipping
   both free — with the local prompt-cache TTFT win LiteLLM can't claim — is
   the sharpest positioning move available.
4. **Governed-MCP completeness** (row 5, #358, then row 7): pagination first
   (correctness), then local-embedding tool search (differentiator).
5. **Agent-identity groundwork** (row 9, watch): SEP-1933/DPoP still draft;
   re-check weekly. Key expiry (#337) + `secret://oauth` (#329) keep daari
   ahead of the curve when it merges.

Standing HITL asks: **approve the five held workflow runs** (PRs #340,
#347–#350), **relax Actions approval for bot PRs**, then **tag + release
v1.4.0** (agent cannot tag/publish).

---

## Changelog

- **2026-09-07** — **Full park:** all five open PRs (#340 + the entire 09-06
  refill #347–#350) held on `action_required`; loop hygiene otherwise verified
  healthy (one comment per stall issue, no re-pick spam). Outward: **LiteLLM
  v1.101.0-rc.1** is a routing offensive — heuristic_v2/hybrid classifiers,
  `user_turn` session pinning, stall escalation, modality routing, context
  escalation — **metered behind an `auto_router` enterprise license** (recorded
  in Positioning); also MCP semantic tool search + `tools/list` pagination fix,
  off-peak pricing, admission control. **Claude Fable 5.1 (09-01) and GPT-6
  Astra (09-03)** shipped at $10/$50 — daari's shipped pricing table still tops
  out at 2024 models → filed [#355](https://github.com/naveenreddyalka/daari/issues/355)
  (P1). Filed [#356](https://github.com/naveenreddyalka/daari/issues/356)
  session affinity, [#357](https://github.com/naveenreddyalka/daari/issues/357)
  stall escalation, [#358](https://github.com/naveenreddyalka/daari/issues/358)
  MCP `nextCursor` pagination (verified in-tree: egress reads page one only).
  New watch rows: tool search, admission control, off-peak pricing. SEP-1933
  still draft; Kong quiet (2.0.3); Ollama v0.34 still rc1; OpenRouter GA'd
  Responses + added BYOK credential restrictions and benchmark-filtered
  `/models`.
- **2026-09-06** — Label HITL ended (labeler #336 works). One park: PR #340
  held on manual CI approval; stall issue #341 re-picked ~12 times → filed
  #342 (dedupe), #343 (ChatGPT Desktop facade, Ollama v0.34-rc1), #344 (budget
  rollover, LiteLLM v1.100 stable), #345 (audit read path). Four shipped rows
  pruned.
- **2026-09-03** — Second full drain in two days: #317–#321 shipped overnight
  (PRs #324–#329). Refill: #330 auto-labeler, #331 key expiry, #332 retention,
  #333 budget webhooks, #334 v1.4.0 prep.
- **2026-09-02** — Backlog drained; table rebuilt. Human unparked both parks
  and merged #293 (Apache 2.0); loop shipped 15 PRs in ~36h (#299–#316).
  Refiled #317–#321. Outward: Kong AI GW 2.0 GA, Portkey v2.20, LiteLLM v1.99.
- **2026-08-28→09-01** (condensed) — First runs: created this PRD; discovered
  the `action_required` park class, the stale search index (#291 → GraphQL
  reads), the closing-keyword hazard (#285→#294), and the PANW/Portkey
  acquisition; filed #275–#279, #285–#289, #294–#297. Relicense #293 opened.
