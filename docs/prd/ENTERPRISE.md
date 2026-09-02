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

## Where daari stands (verified in-tree, 2026-09-02)

**The tree is Apache 2.0** ([#293](https://github.com/naveenreddyalka/daari/pull/293)
merged 2026-09-01, [ADR-0016](../adr/0016-apache-2-relicense.md)) and **the dev
loop is fully unparked**: the human approved held CI runs and applied labels
(#286), and the loop drained the *entire* backlog in ~36 hours — 15 PRs merged
(#299–#316), zero open issues and zero open PRs at the start of this run.

Shipped since the 09-01 scan (former gap-table rows in parentheses):

- OpenAI-compat local backend kind for vLLM/llama.cpp/LM Studio (row 1 →
  [#303](https://github.com/naveenreddyalka/daari/pull/303)); agent prefix L1
  ([#299](https://github.com/naveenreddyalka/daari/pull/299)); SSE keepalive on
  all streaming routes (row 2 → [#304](https://github.com/naveenreddyalka/daari/pull/304)).
- MCP tool allow/deny governance + audit + spec headers (row 3 →
  [#307](https://github.com/naveenreddyalka/daari/pull/307)); MCP Tasks
  extension for long-running `tools/call` (row 10 →
  [#315](https://github.com/naveenreddyalka/daari/pull/315)).
- Cost-split + savings headers `x-daari-response-cost*` (row 4 →
  [#308](https://github.com/naveenreddyalka/daari/pull/308));
  `reasoning_effort` honored end-to-end (row 15 →
  [#312](https://github.com/naveenreddyalka/daari/pull/312)).
- Claude Desktop one-click recipe (row 5 →
  [#309](https://github.com/naveenreddyalka/daari/pull/309)); `daari service
  install --now` ([#300](https://github.com/naveenreddyalka/daari/pull/300));
  upgrade/config-migration guide (row 11 →
  [#316](https://github.com/naveenreddyalka/daari/pull/316)).
- `secret://` references for provider/org keys (row 9 →
  [#314](https://github.com/naveenreddyalka/daari/pull/314)); signed ghcr
  images + SBOM + provenance (row 8 →
  [#311](https://github.com/naveenreddyalka/daari/pull/311)).
- Backlog picker off the search index (park #2 →
  [#305](https://github.com/naveenreddyalka/daari/pull/305)/[#306](https://github.com/naveenreddyalka/daari/pull/306));
  stall triage for `action_required`/suppressed CI
  ([#310](https://github.com/naveenreddyalka/daari/pull/310)).
- Context compression before frontier fallback (former watch row 14) turns out
  to be **already in tree**: `daari/router/compress.py`, opt-in via
  `frontier.compress_context`.

Longer-standing surface (see 08-28 scan): virtual keys + multi-window budgets
+ teams, SSO/OIDC + IdP-minted keys, RBAC, append-only audit, policy sync,
fleet bootstrap, Redis L0/L1 + Postgres ledger/traces, Helm + Grafana,
Prometheus + OTel GenAI, guardrails + PII scrub, MCP ingress (2026-07-28) +
egress, Responses API, Ollama facade, OpenRouter `provider` object (zdr
fail-closed), context-length failover, local backend pool + circuit breakers.
Proof: 1141+ mocked tests; published load (320 rps L0 / 61 ms p95),
vs-LiteLLM, cost-of-pass, agent $0-tier pages.

**Token limits (re-verified 2026-09-02):** this run's token still cannot
label issues (403 `addLabelsToLabelable`) or comment — every issue carries an
"Intended labels:" first line for the human to apply. Never use
closes/fixes/resolves before an issue number in PRD PR bodies.

**Positioning (2026-09-01):** Palo Alto Networks
[acquired Portkey](https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents)
(closed 05-29; now the Prisma AIRS AI Gateway) — developer-first/self-hosted
buyers face roadmap/packaging uncertainty there, though the self-hosted
gateway still ships (v2.20, 2026-09). daari's counter-pitch: Apache 2.0,
run-it-yourself, tokens never leave the building.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **MCP tool-call guardrails** — #307 governs *which* tools; nothing inspects arguments/results flowing through them | 4 | 2 | [Portkey v2.20 MCP Gateway Guardrails](https://portkey.ai/docs/changelog/enterprise) (pre/post-execution checks, structured deny errors); [Kong AI GW 2.0 GA MCP Server Bundling](https://konghq.com/blog/product-releases/kong-ai-gateway-2-0-ga) | Tool payloads (file contents, shell commands) get inspected **on the machine where the tools run** — `GuardrailEngine`, PII scrub, and mcp_policy audit rows already exist to wire in | [#317](https://github.com/naveenreddyalka/daari/issues/317) (P2) |
| 2 | **Tier-decision shadow evals** — cache hits are shadow-sampled (false-hit rate) but no way to measure "would a higher tier have answered differently" before trusting a threshold or learned-routing change | 4 | 3 | [LiteLLM v1.98 auto-router shadow evals](https://docs.litellm.ai/release_notes/v1.98.0/v1-98-0); [v1.100-rc1 operator tiers + `/auto_router/test_routing` dry-run](https://docs.litellm.ai/release_notes/v1.100.0rc1/v1-100-0-rc-1) | LiteLLM replays against a second **paid** deployment; daari replays against the top local tier at **$0** (L6 only under an explicit spend cap) | [#318](https://github.com/naveenreddyalka/daari/issues/318) (P2) |
| 3 | **Budget-remaining headers** — multi-window budgets enforce, but a caller's first signal is the 429; nothing exposes remaining budget per response | 3 | 2 | [Kong cost-based rate limiting + `X-AI-RateLimit-Remaining-*`](https://developer.konghq.com/metering-and-billing/cost-analytics/) | Remaining-$ reflects only real frontier spend ($0 local tiers) and sits next to the `x-daari-response-cost-avoided` header; agents can self-throttle to $0 tiers as budget thins | [#319](https://github.com/naveenreddyalka/daari/issues/319) (P2) |
| 4 | **Streaming usage accounting unproven** — ledger/budgets/savings key off streamed usage, but no test pins running-total vs final-total provider patterns (the Kong Gemini double-count defect class) | 3 | 1 | Kong shipped the fix for this class; LiteLLM v1.99 batch billing is atomically claimed | daari's "$ avoided" and per-team attribution are only as credible as this accounting — it's the number buyers adopt daari for | [#320](https://github.com/naveenreddyalka/daari/issues/320) (P2) |
| 5 | **OAuth client-credentials upstream auth** — `secret://` refs (#314) still resolve to static keys; no token-endpoint-minted short-lived credentials | 3 | 3 | [Portkey v2.20 Workload Identity Federation for OpenAI/Anthropic](https://portkey.ai/docs/changelog/enterprise); [MCP roadmap agent-identity WG](https://modelcontextprotocol.io/development/roadmap) (DPoP, WIF, ID-JAG) | Tokens minted on the machine that uses them — nothing static on disk, no hosted gateway holding org credentials; extends the #314 resolver framework, no new deps | [#321](https://github.com/naveenreddyalka/daari/issues/321) (P3) |
| 6 | **A2A gateway** — no Agent2Agent ingress card or egress governance | 3 | 4 | [Kong Agent Gateway GA](https://konghq.com/blog/product-releases/kong-agent-gateway); A2A under AAIF | Local agents delegating over A2A would get routing/cache/policy without a cloud hop | Watch — revisit when a client daari serves speaks A2A |
| 7 | **MCP server-initiated events + agent identity** — no `subscriptions/listen`; identity work (DPoP/WIMSE/ID-JAG) still WG-stage | 2 | 3 | MCP Tier-1 SDKs; Kong 2.0 GA identity-aware AI policies | Matters once daari fronts long-lived local tool servers; #321 is the first concrete step | Watch — [MCP roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) |
| 8 | **Admin console for keys/teams/budgets** — web dashboard is read-only; key/team/budget management is CLI-only | 3 | 4 | LiteLLM admin UI (React 19, dark mode, key management end-to-end) | CLI-first fits operators; a UI matters at org rollout scale. Wait for operator demand before building a control surface | Watch |
| 9 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API | Local diffusion is a different product; only worth it if IDE clients send it | Non-goal for now |

Open backlog after this run: [#317](https://github.com/naveenreddyalka/daari/issues/317)
(MCP tool-call guardrails, P2), [#318](https://github.com/naveenreddyalka/daari/issues/318)
(tier shadow evals, P2), [#319](https://github.com/naveenreddyalka/daari/issues/319)
(budget headers, P2), [#320](https://github.com/naveenreddyalka/daari/issues/320)
(streaming usage tests, P2), [#321](https://github.com/naveenreddyalka/daari/issues/321)
(`secret://oauth`, P3) — all awaiting human label application ("Intended
labels:" first lines).

---

## Path to enterprise-grade — next 5 milestones

1. **Complete the governed tool plane** (row 1, #317): #307 decides *which*
   tools run; guardrails on arguments/results decide *what may flow through
   them*. Matches the Portkey v2.20 / Kong 2.0 GA headline feature — but the
   payloads never leave the machine.
2. **Learned routing you can audit** (row 2, #318): shadow-sampled tier
   divergence is the number that lets an operator turn thresholds up (or trust
   `daari learn deploy`) without faith. Answers LiteLLM's shadow evals at $0.
3. **Close the FinOps loop** (rows 3–4, #319/#320): remaining-budget headers on
   every response + proof that streamed usage is counted exactly once. The
   savings claims are the product; make them header-scrapeable and test-pinned.
4. **Keyless upstream auth** (row 5, #321): `secret://oauth` client-credentials
   resolver — where Portkey WIF and the MCP identity roadmap are converging.
5. **Distribution** (HITL): with Apache 2.0 merged and images signed (#311),
   tag/release v1.4.0 and publish to PyPI/ghcr — releases stay human-only
   (AGENTS.md hard limit). This is now the top standing ask.

Standing HITL asks: **tag + release v1.4.0** (first Apache-2.0 release; agent
cannot tag/publish), and **apply labels to #317–#321** (token still 403s on
labeling).

---

## Changelog

- **2026-09-02** — **Backlog drained; table rebuilt.** The human unparked both
  parks and merged [#293](https://github.com/naveenreddyalka/daari/pull/293)
  (Apache 2.0); the loop shipped 15 PRs in ~36h (#299–#316), closing every
  open issue — 11 gap-table rows pruned as shipped (incl. watch row 14, found
  already in tree as `daari/router/compress.py`). Zero open issues/PRs at run
  start, so this run refiled the backlog: [#317](https://github.com/naveenreddyalka/daari/issues/317)
  MCP tool-call guardrails, [#318](https://github.com/naveenreddyalka/daari/issues/318)
  tier shadow evals, [#319](https://github.com/naveenreddyalka/daari/issues/319)
  budget-remaining headers, [#320](https://github.com/naveenreddyalka/daari/issues/320)
  streaming-usage test pin, [#321](https://github.com/naveenreddyalka/daari/issues/321)
  `secret://oauth` resolver (token still cannot label — 403 re-verified).
  Outward delta: **Kong AI Gateway 2.0 GA'd 09-01** (the long-awaited "2.1"
  scope: MCP Server Bundling, modality-aware cost management, identity-aware
  policies, Kimi/MS Foundry/SageMaker providers; AI plugins become opt-in at
  Kong Gateway 3.18); **Portkey v2.20** (MCP Gateway Guardrails → row 1, WIF
  for OpenAI/Anthropic → row 5, unified gateway+MCP single-port mode);
  **LiteLLM v1.99.0 stable 09-01** + v1.100-rc1 (access-group shared budgets
  with rollover, operator-defined router tiers + routing dry-run endpoint →
  row 2); Ollama 0.33.2 / vLLM 0.28.0 unchanged; llama.cpp runs semver
  (v0.3.0) *and* nightly build tags (b10760) in parallel.
- **2026-09-01** — Relicense PR #293 went `DIRTY` (conflicted with daily PRD
  merges); recorded the **Palo Alto Networks acquired Portkey** positioning
  fact; filed [#297](https://github.com/naveenreddyalka/daari/issues/297)
  (`reasoning_effort` silently dropped — shipped next day as #312). LiteLLM
  v1.99.0 highlights noted. Both parks persisted (day 4).
- **2026-08-31** — Human opened Apache 2.0 relicense PR #293. Found #285
  auto-closed by a PRD PR closing keyword → re-filed as #294; standing rule:
  no closing keywords in PRD PR bodies. Converted row 8 →
  [#295](https://github.com/naveenreddyalka/daari/issues/295) (cosign + SBOM).
  Portkey v2.19, OpenRouter hosted MCP + Batch API noted.
- **2026-08-30** — Found park #2: GitHub search index stale for this repo;
  `gh issue list --label` returned zero of the labeled issues → filed
  [#291](https://github.com/naveenreddyalka/daari/issues/291) (picker onto the
  GraphQL repository connection). vLLM 0.28.0; llama.cpp semver v0.3.0; MCP
  roadmap (server-initiated events, agent identity) → watch row.
- **2026-08-29** — Found park #1: PRs stalled on `action_required` CI approval,
  issues filed unlabeled (token 403) → filed #285/#286 (HITL unblock),
  #287–#289. MCP Tasks SDK watch condition met.
- **2026-08-28** — First run. Created this PRD; scanned MCP `2026-07-28`
  stateless spec, A2A v1.0, Kong 3.14, LiteLLM v1.98, Portkey MCP Gateway GA,
  Ollama 0.33; filed #275–#279 (rows 1–5).
