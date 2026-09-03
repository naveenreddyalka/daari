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

## Where daari stands (verified in-tree, 2026-09-03)

**The loop is running at full speed.** Yesterday's five issues (#317–#321)
all shipped within ~9 hours of the human applying labels — PRs
[#324](https://github.com/naveenreddyalka/daari/pull/324)–[#329](https://github.com/naveenreddyalka/daari/pull/329)
merged overnight, and the backlog was empty again at the start of this run:

- MCP guardrails on `tools/call` arguments/results, ingress + egress, shared
  `GuardrailEngine`, audit rows ([#325](https://github.com/naveenreddyalka/daari/pull/325)).
- Tier-decision shadow evals: sampled replay against a comparison tier, $0 by
  default, surfaced in `daari learn stats` / `daari report` / Prometheus
  ([#326](https://github.com/naveenreddyalka/daari/pull/326)).
- Budget-remaining headers `x-daari-budget-remaining/-limit/-window/-reset/-scope`
  on every response and on 402s ([#327](https://github.com/naveenreddyalka/daari/pull/327)).
- Streaming usage counted exactly once across OpenAI SSE, `/v1/messages`,
  Ollama facade, and cancellation — four real defects found and fixed
  ([#328](https://github.com/naveenreddyalka/daari/pull/328)).
- `secret://oauth` client-credentials resolver with cached short-lived tokens,
  wired into every L6 attempt ([#329](https://github.com/naveenreddyalka/daari/pull/329)).
- Plus `daari service restart` ([#324](https://github.com/naveenreddyalka/daari/pull/324)).

Longer-standing surface (see 08-28/09-02 scans): Apache 2.0
([ADR-0016](../adr/0016-apache-2-relicense.md)), virtual keys + multi-window
budgets + teams + per-key RPM/TPM (Redis-backed for fleets), SSO/OIDC +
IdP-minted keys, RBAC, append-only audit, policy sync, fleet bootstrap,
Redis L0/L1 + Postgres ledger/traces, Helm + Grafana, Prometheus + OTel GenAI,
guardrails + PII scrub (chat + MCP), MCP ingress (2026-07-28, Tasks) + egress
governance, Responses API, `/v1/embeddings`, Ollama facade, OpenAI-compat local
backends (vLLM/llama.cpp/LM Studio), OpenRouter `provider` object, per-model +
cached-input pricing, context-length failover + compression, circuit breakers,
signed images + SBOM. Proof: 1141+ mocked tests; published load (320 rps L0 /
61 ms p95), vs-LiteLLM, cost-of-pass pages.

**Token limits (re-verified 2026-09-03):** labeling still 403s
(`addLabelsToLabelable` FORBIDDEN) — [#330](https://github.com/naveenreddyalka/daari/issues/330)
now targets automating it with an in-repo labeler workflow. Until it lands,
every issue carries an "Intended labels:" first line for the human. Never use
closes/fixes/resolves before an issue number in PRD PR bodies.

**Positioning (unchanged):** Palo Alto Networks
[acquired Portkey](https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents)
(now the Prisma AIRS AI Gateway) — developer-first/self-hosted buyers face
roadmap uncertainty there. daari's counter-pitch: Apache 2.0,
run-it-yourself, tokens never leave the building.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Issue auto-labeler** — token cannot label (403, day 7); every backlog refill parks the loop until a human applies "Intended labels:" lines | 4 | 1 | n/a (loop health) | Removes the last recurring human dependency in the autonomous dev loop; issues become pickable at filing time | [#330](https://github.com/naveenreddyalka/daari/issues/330) (P1) |
| 2 | **Virtual key expiry** — keys have `revoked_at` but no `expires_at`; SSO-minted keys outlive the IdP session forever | 4 | 2 | [LiteLLM key `duration`](https://docs.litellm.ai/docs/proxy/virtual_keys); [MCP agent-identity roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) pushes short-lived credentials | Expiry enforced at the gateway on the operator's own box; IdP-minted keys track the IdP session. #329 did short-lived *upstream* creds — inbound keys should match | [#331](https://github.com/naveenreddyalka/daari/issues/331) (P2) |
| 3 | **Data retention / prune** — traces, ledger, audit, shadow checks, MCP tasks grow forever; no retention period to state in a compliance answer | 3 | 2 | [LiteLLM spend-log retention + cleanup job](https://docs.litellm.ai/docs/proxy/spend_logs_deletion) | "Traces live N days, on your disk, then they're gone" — retention on the box that owns the data, no vendor data processor | [#332](https://github.com/naveenreddyalka/daari/issues/332) (P2) |
| 4 | **Budget alert webhooks** — callers see #319 headers; the operator learns a team burned its month from 402s in logs | 3 | 2 | [LiteLLM Slack/webhook alerting](https://docs.litellm.ai/docs/proxy/alerting); Kong Konnect cost analytics | Plain webhook from the gateway box (Slack-compatible, ntfy, internal hooks) — spend data never leaves the building; `WindowStatus` already computed per request | [#333](https://github.com/naveenreddyalka/daari/issues/333) (P2) |
| 5 | **v1.4.0 unshipped** — pyproject + last tag still v1.3.0 while main holds the relicense, signed images, MCP governance, and the FinOps loop | 3 | 1 | n/a (distribution) | First release a company can legally adopt (Apache 2.0) and verify (cosign); agent preps notes + version bump, human tags | [#334](https://github.com/naveenreddyalka/daari/issues/334) (P2, prep only — tag/release stays HITL) |
| 6 | **Batch API** — no `/v1/batches`; agents and eval pipelines increasingly submit batch jobs | 4 | 4 | [OpenRouter Batch API (beta)](https://openrouter.ai/docs); LiteLLM e2e batch billing (v1.99) | The local-first story is unmatched: drain batches through idle local tiers overnight at $0. MCP Tasks store (#315) is a template for background work + result retrieval | File when a daari-served client sends batches; sketch first |
| 7 | **Budget rollover** — unused window headroom evaporates; LiteLLM v1.100-rc adds opt-in rollover on access-group budgets | 2 | 2 | [LiteLLM v1.100-rc1](https://docs.litellm.ai/release_notes/v1.100.0rc1/v1-100-0-rc-1) | Small parity item on top of multi-window budgets | Watch — file if an operator asks or v1.100 goes stable with it headline |
| 8 | **Gemini-native facade** — no `/v1beta` `generateContent`; Gemini CLI and Gemini-native SDK agents cannot point at daari | 3 | 4 | Nobody self-hosted; OpenRouter translates server-side | Same trick as the Ollama facade and Anthropic gateway: speak the client's dialect locally, route to any tier | Watch — file when a target client (e.g. Gemini CLI custom base URL) is confirmed |
| 9 | **A2A gateway** — no Agent2Agent ingress card or egress governance | 3 | 4 | [Kong Agent Gateway](https://konghq.com/blog/product-releases/kong-agent-gateway); A2A under AAIF | Local agents delegating over A2A would get routing/cache/policy without a cloud hop | Watch — revisit when a client daari serves speaks A2A |
| 10 | **MCP server-initiated events + agent identity** — no `subscriptions/listen`; DPoP/WIMSE/ID-JAG still WG-stage | 2 | 3 | MCP Tier-1 SDKs; Kong 2.0 identity-aware policies | Matters once daari fronts long-lived local tool servers; #329 + #331 are the concrete steps | Watch — [MCP roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) |
| 11 | **Admin console for keys/teams/budgets** — web dashboard read-only; management is CLI-only | 3 | 4 | LiteLLM admin UI (React 19, key management end-to-end) | CLI-first fits operators; a UI matters at org rollout scale | Watch — wait for operator demand |
| 12 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API | Local diffusion is a different product | Non-goal for now |

Open backlog after this run: [#330](https://github.com/naveenreddyalka/daari/issues/330)
(auto-labeler, P1), [#331](https://github.com/naveenreddyalka/daari/issues/331)
(key expiry, P2), [#332](https://github.com/naveenreddyalka/daari/issues/332)
(retention, P2), [#333](https://github.com/naveenreddyalka/daari/issues/333)
(budget alerts, P2), [#334](https://github.com/naveenreddyalka/daari/issues/334)
(v1.4.0 prep, P2) — all awaiting human label application until #330 lands.

---

## Path to enterprise-grade — next 5 milestones

1. **Close the loop's last human dependency** (row 1, #330): an in-repo
   labeler workflow makes every future backlog refill self-serve. One tiny
   authorized workflow file ends a 7-day-old standing HITL ask.
2. **Credential lifecycle** (row 2, #331): key expiry + SSO key TTL completes
   the identity story #329 started — short-lived credentials on both sides of
   the gateway, matching where the MCP identity roadmap is heading.
3. **Compliance-grade data hygiene** (rows 3–4, #332/#333): a statable
   retention period and proactive budget alerts are what an ops team audits
   for before running any gateway in production.
4. **Ship v1.4.0** (row 5, #334 + HITL): the agent preps release notes and
   the version bump; the human tags and publishes. First Apache-2.0,
   cosign-verifiable release — distribution is the bottleneck, not features.
5. **Batch lane** (row 6): sketch `/v1/batches` drained through idle local
   tiers at $0 — the next differentiator no cloud gateway can copy, queued
   behind confirmed client demand.

Standing HITL asks: **tag + release v1.4.0** once #334 lands (agent cannot
tag/publish), and **apply labels to #330–#334** (last manual round if #330
merges).

---

## Changelog

- **2026-09-03** — **Second full drain in two days:** #317–#321 all shipped
  overnight (PRs [#324](https://github.com/naveenreddyalka/daari/pull/324)–[#329](https://github.com/naveenreddyalka/daari/pull/329)),
  backlog empty again at run start; five shipped rows pruned. Outward scan
  quiet (Portkey v2.20, Kong 2.0.3, LiteLLM v1.99 stable / v1.100-rc1,
  vLLM 0.28.0 all unchanged; Ollama 0.33.3-rc2 out). Inward scan drove this
  refill: [#330](https://github.com/naveenreddyalka/daari/issues/330) issue
  auto-labeler (labeling 403 re-verified day 7; authorizes one workflow file),
  [#331](https://github.com/naveenreddyalka/daari/issues/331) virtual key
  expiry + SSO key TTL, [#332](https://github.com/naveenreddyalka/daari/issues/332)
  retention/prune for traces/ledger/audit,
  [#333](https://github.com/naveenreddyalka/daari/issues/333) budget alert
  webhooks, [#334](https://github.com/naveenreddyalka/daari/issues/334)
  v1.4.0 release prep (tag stays HITL). New table rows: batch API through
  idle local tiers (row 6), budget rollover watch (row 7), Gemini-native
  facade watch (row 8). Verified in-tree before filing: embeddings endpoint,
  per-key RPM/TPM, cached-input pricing all already exist.
- **2026-09-02** — **Backlog drained; table rebuilt.** Human unparked both
  parks and merged [#293](https://github.com/naveenreddyalka/daari/pull/293)
  (Apache 2.0); the loop shipped 15 PRs in ~36h (#299–#316) closing every
  open issue — 11 gap-table rows pruned as shipped. Refiled the backlog:
  #317 MCP tool-call guardrails, #318 tier shadow evals, #319
  budget-remaining headers, #320 streaming-usage test pin, #321
  `secret://oauth`. Outward: **Kong AI Gateway 2.0 GA 09-01** (MCP Server
  Bundling, modality-aware cost mgmt, identity-aware policies); **Portkey
  v2.20** (MCP Gateway Guardrails, WIF); **LiteLLM v1.99.0 stable** +
  v1.100-rc1 (access-group budgets w/ rollover, operator router tiers).
- **2026-09-01** — Relicense PR #293 went `DIRTY`; recorded the **Palo Alto
  Networks acquired Portkey** positioning fact; filed #297
  (`reasoning_effort` dropped — shipped next day as #312).
- **2026-08-31** — Human opened Apache 2.0 relicense PR #293. Found #285
  auto-closed by a PRD PR closing keyword → re-filed as #294; standing rule:
  no closing keywords in PRD PR bodies. Converted row 8 → #295 (cosign+SBOM).
- **2026-08-30** — Found park #2: GitHub search index stale;
  `gh issue list --label` lies → filed #291 (picker onto GraphQL). MCP
  roadmap (server-initiated events, agent identity) → watch row.
- **2026-08-29** — Found park #1: PRs stalled on `action_required`, issues
  unlabeled (token 403) → filed #285/#286 (HITL unblock), #287–#289.
- **2026-08-28** — First run. Created this PRD; filed #275–#279.
