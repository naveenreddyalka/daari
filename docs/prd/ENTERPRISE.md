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

## Where daari stands (verified in-tree, 2026-09-08)

**Nine done PRs are parked on Actions approval — fifth consecutive day.**
The 09-07 refill (#355–#358) was implemented within hours as PRs
[#360](https://github.com/naveenreddyalka/daari/pull/360)–[#363](https://github.com/naveenreddyalka/daari/pull/363),
then held on `action_required` exactly like
[#340](https://github.com/naveenreddyalka/daari/pull/340) and
[#347](https://github.com/naveenreddyalka/daari/pull/347)–[#350](https://github.com/naveenreddyalka/daari/pull/350)
before them. No feature code has merged since 09-03. Loop hygiene stays
healthy: one stall issue per new PR (#364–#367), one comment each, no re-pick
spam.

**The drain itself is now a hazard.** Branch protection requires up-to-date
branches (five PRs already show `BEHIND`), so approving one run merges one PR
and strands the other eight — each then needs a branch update, a fresh CI run,
and *another* manual approval. Worst case the human clicks through ~9 rounds.
Two mitigations, in order of value: **relax the Actions approval policy for
repo-workflow bot PRs** (one setting, ends the park class), and the new
auto-drain issue filed this run (the PR watcher merges `origin/main` into
`BEHIND` auto-merge PRs itself —
[#368](https://github.com/naveenreddyalka/daari/issues/368), gap table row 2).

Longer-standing surface (see 08-28→09-07 scans): Apache 2.0
([ADR-0016](../adr/0016-apache-2-relicense.md)), virtual keys + multi-window
budgets + teams + per-key RPM/TPM/**in-flight caps** + key/SSO expiry,
SSO/OIDC + IdP-minted keys, RBAC, append-only audit, retention/prune, policy
sync, fleet bootstrap, Redis L0/L1 + Postgres ledger/traces, Helm + Grafana,
Prometheus + OTel GenAI, budget headers + threshold webhooks, guardrails +
PII scrub (chat + MCP), MCP ingress (2026-07-28, Tasks) + egress governance
with per-key/team tool governance, `secret://` refs incl. OAuth
client-credentials, Responses API, `/v1/embeddings`, Ollama facade,
OpenAI-compat local backends (vLLM/llama.cpp/LM Studio), OpenRouter
`provider` object, per-model + cached-input pricing, context-length failover +
compression, circuit breakers, signed images + SBOM, shadow evals. Proof:
1141+ mocked tests; published load (320 rps L0 / 61 ms p95), vs-LiteLLM,
cost-of-pass pages. Parked in the nine PRs above: v1.4.0 prep, stall re-pick
dedupe, ChatGPT Desktop facade, budget rollover, audit export, pricing
refresh, session affinity, stall escalation, MCP `tools/list` pagination.

**Positioning:** Portkey is the PANW Prisma AIRS AI Gateway (changelog quiet
since April). LiteLLM's routing offensive continues as a daily blog cadence:
[per-hop classifier compression](https://docs.litellm.ai/blog/auto-router-per-hop-compression)
(09-05), [subtask/phase routing](https://docs.litellm.ai/blog/subtask-type-routing)
(09-07, experimental — explore/verify/implement phases each routed to a
different tier; Opus-fixed quality at 46% less cost on a SWE-bench subset),
[stall escalation](https://docs.litellm.ai/blog/auto-router-stall-escalation)
(09-08 — the feature daari has parked in #362). Customization stays metered
behind the `auto_router` enterprise license. daari's counter-pitch is
unchanged and sharpening: routing *is* the Apache 2.0 core, run-it-yourself,
tokens never leave the building.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Nine done PRs parked on Actions approval** — v1.4.0 prep + both refills (09-06, 09-07) held on `action_required`; fifth consecutive day; strict up-to-date branch protection makes the drain itself ~9 manual rounds | 5 | 0 | n/a (policy) | n/a — human-only | HITL: **relax bot-PR Actions approval policy** (preferred, ends the class) or approve held runs for [#340](https://github.com/naveenreddyalka/daari/pull/340), [#347](https://github.com/naveenreddyalka/daari/pull/347)–[#350](https://github.com/naveenreddyalka/daari/pull/350), [#360](https://github.com/naveenreddyalka/daari/pull/360)–[#363](https://github.com/naveenreddyalka/daari/pull/363) as they re-queue; then tag v1.4.0 |
| 2 | **PR watcher can't drain a park** — `autodev_pr_watch.py` classifies and comments but never remediates; `BEHIND` auto-merge PRs wait for a human to click *Update branch* nine times | 4 | 2 | n/a (loop plumbing) | Makes the backlog self-draining the moment approval lands (or the policy relaxes) | [#368](https://github.com/naveenreddyalka/daari/issues/368) (P2) |
| 3 | **Budget alert double-fire on multi-replica** — webhook dedupe is in-process (`budget_alerts.py` docstring caveat); an HA fleet pages twice per threshold | 3 | 2 | LiteLLM (Redis-backed alert state) | Redis is already in the stack (L0/L1); one `SET NX EX` per crossing makes alerts exactly-once per fleet | [#369](https://github.com/naveenreddyalka/daari/issues/369) (P2) |
| 4 | **Agent-loop routing parity — implemented, parked**: pricing refresh [#360](https://github.com/naveenreddyalka/daari/pull/360), session affinity [#361](https://github.com/naveenreddyalka/daari/pull/361), stall escalation [#362](https://github.com/naveenreddyalka/daari/pull/362), MCP pagination [#363](https://github.com/naveenreddyalka/daari/pull/363) | 4 | 0 | LiteLLM v1.101-rc.1 (behind enterprise license) | Free + local prompt-cache TTFT win | Unpark row 1; nothing left to build |
| 5 | **Subtask/phase routing** — no per-agent-phase tiering (explore/verify/implement); LiteLLM's 09-07 experiment matched fixed-Opus quality at 46% less cost | 4 | 3 | [LiteLLM subtask classifier](https://docs.litellm.ai/blog/subtask-type-routing) (experimental) | Phase detection from tool history is stateless and local; explore-phase turns are exactly what $0 local tiers are for — the cost win compounds | Watch — file after #361/#362 merge (builds on their tool-history machinery; filing now guarantees conflicts with parked router PRs) |
| 6 | **Batch API** — no `/v1/batches`; agents and eval pipelines increasingly submit batch jobs | 4 | 4 | OpenRouter Batch API (beta); LiteLLM e2e batch billing | Drain batches through idle local tiers overnight at $0 — no cloud gateway can copy it. MCP Tasks store (#315) is the template | File when a daari-served client sends batches; sketch first |
| 7 | **MCP semantic tool search** — big tool catalogs drown agent context; no server-side relevance ranking | 3 | 3 | LiteLLM `mcp_tool_search` (embedding-ranked) | `/v1/embeddings` + local embed models → $0 ranking on-box | Watch — file after #363 lands and a daari-served client hits a large catalog |
| 8 | **Global admission control** — per-key in-flight caps shipped (#169, `rate_limit.py`); missing only a worker-level cap / fast 503 when local backends saturate across keys | 2 | 3 | [LiteLLM `max_in_flight_requests_per_worker`](https://docs.litellm.ai/release_notes/v1.101.0rc1/v1-101-0-rc-1) | Local GPUs saturate long before the gateway; failing fast beats queueing into timeout | Watch — file when a load report shows queue collapse, or with the next HA milestone |
| 9 | **MCP agent identity** — [WIF SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) + DPoP SEP-1932 both still **draft** (re-checked 09-08) | 3 | 3 | MCP Tier-1 SDKs; LiteLLM MCP session RFC 7662 | Workload JWTs (K8s/SPIFFE) as inbound auth fit fleets; `secret://oauth` + key expiry are the groundwork | Watch — file when SEP-1933 merges or a fleet asks |
| 10 | **Gemini-native facade** — no `/v1beta` `generateContent`; Gemini CLI can't point at daari | 3 | 4 | Nobody self-hosted | Same dialect-facade trick as Ollama/Anthropic | Watch — file when a target client is confirmed |
| 11 | **A2A gateway** — no Agent2Agent ingress/egress governance | 3 | 4 | Kong Agent Gateway | Local agents delegating over A2A get routing/cache/policy without a cloud hop | Watch — revisit when a daari-served client speaks A2A |
| 12 | **Admin console** — web dashboard read-only; key/team/budget management is CLI-only | 3 | 4 | LiteLLM admin UI | CLI-first fits operators; a UI matters at org rollout scale | Watch — wait for operator demand |
| 13 | **Off-peak pricing windows** — some providers discount by time window; daari prices flat per model | 2 | 2 | LiteLLM `off_peak_pricing` | Local math at cost time; pairs with rollover (#349) | Watch — file when a provider daari routes to publishes off-peak rates |
| 14 | **Per-request `cost_tier` body param** — OpenRouter Auto router takes it in-body; daari has `X-Daari-Tier-Cap` header + profiles | 2 | 2 | OpenRouter Auto router | Header + `.daari.yaml` cover most cases | Watch — file if a client can't set headers |
| 15 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API | Local diffusion is a different product | Non-goal for now |

Open backlog after this run:
[#368](https://github.com/naveenreddyalka/daari/issues/368) (PR-watch
auto-drain, P2) and [#369](https://github.com/naveenreddyalka/daari/issues/369)
(budget-alert fleet dedupe, P2) — both auto-labeled at filing — are the only
*pickable* items; every other open
issue has a parked PR or is a stall tracker (#341, #351–#354, #364–#367 — all
resolve with the approvals in row 1). Deliberately filed 2 of the 5-issue
budget: with nine PRs parked, more issues would only manufacture conflicting
parked branches.

---

## Path to enterprise-grade — next 5 milestones

1. **Unpark the pipeline** (row 1, human-only): relax the Actions approval
   policy for repo-workflow bot PRs — five parks in eleven days, nine PRs
   deep, and strict branch protection turns the drain into ~9 manual rounds.
   One policy change ends the class; approving runs one-by-one is the slow
   alternative. Then tag v1.4.0.
2. **Make the loop self-draining** (row 2,
   [#368](https://github.com/naveenreddyalka/daari/issues/368)): the PR watcher merges
   `origin/main` into `BEHIND` auto-merge PRs (union-merging
   `docs/TRACKING.md`) so the stack drains itself once checks can run.
3. **Ship the parked agent-loop routing suite** (row 4): pricing accuracy,
   session affinity, stall escalation, MCP pagination are all done — they beat
   LiteLLM's enterprise-licensed equivalents at $0 the moment they merge.
4. **Phase routing is the next routing frontier** (row 5, watch): LiteLLM's
   subtask experiment validates daari's core thesis — most agent turns are
   cheap-model turns. File immediately after #361/#362 merge.
5. **Fleet-grade correctness polish** (row 3,
   [#369](https://github.com/naveenreddyalka/daari/issues/369)): exactly-once budget
   alerts on multi-replica; pairs with the HA/observability story that
   retention (#338) and webhooks (#339) started.

Standing HITL asks: **relax bot-PR Actions approval** (or approve the nine
held runs), close stall issues #341/#351–#354/#364–#367 after merges, then
**tag + release v1.4.0** (agent cannot tag/publish).

---

## Changelog

- **2026-09-08** — **Park deepened: nine PRs held** (#340, #347–#350,
  #360–#363 — the entire 09-07 refill implemented within hours, then parked;
  fifth consecutive day). Identified the drain hazard: strict up-to-date
  branch protection means sequential approve/update rounds. Filed
  [#368](https://github.com/naveenreddyalka/daari/issues/368) **PR-watch
  auto-drain** (P2) and
  [#369](https://github.com/naveenreddyalka/daari/issues/369) **budget-alert
  fleet dedupe** (P2); deliberately stopped at 2/5 issues to avoid
  manufacturing conflicting parked PRs.
  Outward: LiteLLM blog cadence — per-hop classifier compression (09-05),
  **subtask/phase routing** (09-07, new watch row 5), stall escalation post
  (09-08, parity already parked in #362); Ollama still v0.34.0-rc1; Kong
  quiet (2.0.3); SEP-1933 still draft; OpenRouter adds STT
  timestamps/segments, workspace members API, guardrail training-consent
  flags. Inward verified: per-key in-flight caps already shipped (#169) —
  admission-control row corrected; `budget_alerts.py` dedupe is in-process
  (docstring caveat confirmed).
- **2026-09-07** — Full park (five PRs). Outward: LiteLLM v1.101.0-rc.1
  routing offensive metered behind `auto_router` enterprise license; Claude
  Fable 5.1 + GPT-6 Astra at $10/$50. Filed #355 pricing (P1), #356 session
  affinity, #357 stall escalation, #358 MCP pagination.
- **2026-09-06** — Label HITL ended (labeler #336 works). One park (#340);
  stall issue #341 re-picked ~12× → filed #342 dedupe, #343 ChatGPT Desktop
  facade, #344 budget rollover, #345 audit read path.
- **2026-09-03** — Second full drain in two days (#317–#321 → PRs #324–#329
  overnight). Refill: #330 auto-labeler, #331 key expiry, #332 retention,
  #333 budget webhooks, #334 v1.4.0 prep.
- **2026-09-02** — Backlog drained; human unparked both parks; Apache 2.0
  merged; loop shipped 15 PRs in ~36h (#299–#316). Refiled #317–#321.
- **2026-08-28→09-01** (condensed) — Created this PRD; discovered the
  `action_required` park class, the stale search index (→ GraphQL reads), the
  closing-keyword hazard, the PANW/Portkey acquisition; filed #275–#279,
  #285–#289, #294–#297.
