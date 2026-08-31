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

## Where daari stands (verified in-tree, 2026-08-28)

Enterprise surface already shipped — deeper than ARCHITECTURE.md (v1.2.0) records:

- **Auth & tenancy:** virtual keys with multi-window budgets + team hierarchy (#174),
  RPM rate limits, SSO/OIDC (RS/ES JWKS) with IdP-claim-minted keys (#176),
  RBAC (`daari/enterprise/rbac.py`), append-only audit (`audit.py`), fleet
  bootstrap + signed policy sync.
- **HA & deploy:** Redis L0/L1 backends (optimistic-lock puts, #150), Postgres
  ledger/traces, stateless replicas, Helm chart + Grafana (`deploy/`), local
  backend pool with health checks + circuit breakers (#170), `/ready`.
- **Observability:** Prometheus, OTel GenAI semconv (#167), per-request traces,
  usage ledger with savings + per-client/team attribution, web dashboard.
- **Gateway parity:** Responses API, Anthropic + tool passthrough, MCP ingress
  (negotiates up to `2026-07-28`) + MCP egress client, Ollama facade, guardrails,
  PII scrub, boundaries (B0–B3), OpenRouter `provider` object incl. `zdr`
  fail-closed (#224), context-length failover (#244).
- **Proof:** 1135 mocked tests; published load (320 rps L0 / 61 ms p95), vs-LiteLLM
  (~27× on $0 tiers), cost-of-pass, and agent $0-tier (100% of 8) pages.

**Adoption blockers that are HITL, not eng:** the daemon is Apache 2.0
([ADR-0016](../adr/0016-apache-2-relicense.md) / #227). PyPI/ghcr publishing
stays user-gated.

**Loop health (2026-08-30): doubly parked.** Park #1 (human action,
[#286](https://github.com/naveenreddyalka/daari/issues/286)): PRs
[#281](https://github.com/naveenreddyalka/daari/pull/281)/[#283](https://github.com/naveenreddyalka/daari/pull/283)
still await manual CI-run approval; issues #275–#279 and #285–#289 still
**unlabeled** (token cannot label/comment — 403s verified 08-29). Park #2
(new, [#291](https://github.com/naveenreddyalka/daari/issues/291)): GitHub's
search index for this repo went stale — it returns 2 of 14 open items and
zero matches for any label — and `gh issue list --label auto-dev` routes
through GraphQL *search*, so the picker sees "backlog empty" and every
scheduled `autodev-cycle` run no-ops green. Only the GraphQL repository
connection (`repository.issues(labels:[...])`) returns correct data; #291
moves the picker and the regression dedupe onto it. Even after a human
unparks #286, the loop stays dead until #291 lands (or the index recovers).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **OpenAI-compat local backend kind** — local tiers only speak Ollama/MLX; no first-class vLLM / llama.cpp server / LM Studio / SGLang slot | 5 | 2 | [Kong 3.14 added vLLM provider](https://konghq.com/blog/product-releases/kong-ai-gateway-3-14); LiteLLM 100+ providers | Enterprises standardize GPU pools on vLLM; daari's gateway-heavy topology (ROADMAP-v2 F4) is fiction without it. Pool/breaker plumbing (#170) already abstracts slots | [#275](https://github.com/naveenreddyalka/daari/issues/275) (P1) |
| 2 | **SSE keepalive heartbeat** — no ping on streaming routes; cold model loads (30s+) send zero bytes and LBs/tunnels/IDEs time out | 4 | 1 | [LiteLLM v1.98 global + per-deployment keepalive](https://docs.litellm.ai/release_notes/) | daari sits behind cloudflared tunnels (Cursor BYOK) where idle timeouts are the default failure; local cold-start is our worst case, not theirs | [#276](https://github.com/naveenreddyalka/daari/issues/276) (P1) |
| 3 | **MCP tool governance** — `/mcp` ingress + egress have no per-key/team tool allow/deny, no audit rows, no `Mcp-Method`/`Mcp-Name` headers | 4 | 2 | [Portkey MCP Gateway GA](https://portkey.ai/docs/changelog/2026/january) (registry, RBAC per tool, logs); Kong MCP gateway | Tool calls carry the most sensitive payloads; governing them on-device beats shipping them to a hosted gateway. RBAC/audit/policy modules already exist to wire in | [#277](https://github.com/naveenreddyalka/daari/issues/277) (P2) |
| 4 | **Cost-split response headers** — `daari_meta` has cost but no header contract FinOps tooling can scrape per response | 3 | 1 | [LiteLLM `x-litellm-response-cost-*`](https://docs.litellm.ai/release_notes/); [Kong cost analytics + `X-AI-RateLimit-Remaining-*` budget headers now documented](https://developer.konghq.com/metering-and-billing/cost-analytics/) | daari can also report **$ avoided** (frontier-implied vs $0 local) per response — a number no proxy can honestly print. Kong's remaining-budget header pattern is a natural scope add (daari already 429s with `Retry-After`) | [#278](https://github.com/naveenreddyalka/daari/issues/278) (P2) |
| 5 | **Claude Desktop one-click** — Ollama 0.33 made Claude Desktop a third-party-gateway client; daari has no recipe | 3 | 2 | [Ollama 0.33](https://github.com/ollama/ollama/releases/tag/v0.33.0) | daari already ships an Ollama facade + recipe framework; pointing Claude Desktop at daari adds cache/routing/budgets Ollama alone lacks | [#279](https://github.com/naveenreddyalka/daari/issues/279) (P2) |
| 6 | **A2A v1.0 gateway** — no Agent2Agent support (ingress agent card or egress governance) | 3 | 4 | [Kong Agent Gateway GA](https://konghq.com/blog/product-releases/kong-agent-gateway); [A2A joined the AAIF 2026-08-17](https://forkast.news/googles-a2a-protocol-joins-aaif-consolidating-the-agent-economys-protocol-layer-under-one-roof/) (governance only, no spec change) | Local agents delegating over A2A would get routing/cache/policy without a cloud hop | Watch — revisit when a client daari serves speaks A2A |
| 7 | **Router shadow evals** — no way to measure "would L6 have answered differently" on sampled live traffic before trusting a threshold change | 3 | 3 | [LiteLLM v1.98 auto-router shadow evals](https://docs.litellm.ai/release_notes/v1.98.0/v1-98-0) | daari already shadow-samples cache hits (false-hit rate); extending to tier decisions makes learned routing auditable | Backlog once #269 merges (implementation done in stalled [PR #281](https://github.com/naveenreddyalka/daari/pull/281)) |
| 8 | **Signed images + SBOM** — ghcr image unsigned, no SBOM/provenance | 3 | 2 | LiteLLM signs with cosign (v1.97+) | Table stakes for enterprise supply-chain review | Needs an issue that explicitly authorizes the workflow edit (AGENTS.md hard limit) |
| 9 | **Secret references / vault-backed keys** — frontier + org keys live in env/config | 3 | 3 | [Portkey vault-backed credentials](https://portkey.ai/docs/changelog/2026/march.md) | Keys never leave the machine today; `secret://` refs resolved from keychain/exec/env-file keep that story while passing security review — no vault SDK needed | [#288](https://github.com/naveenreddyalka/daari/issues/288) (P3) |
| 10 | **MCP Tasks extension** — `2026-07-28` negotiated, but long-running `tools/call` still blocks the request; no `tasks/get`/`update`/`cancel` | 3 | 3 | [All four Tier-1 SDKs now ship 2026-07-28 + Tasks](https://developers.googleblog.com/scaling-ai-agent-infrastructure-with-the-mcp-stateless-updates/) (Go v1.7.0 day-one, C# v2.0.0); [spec blog](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) | Long local commands (test suites, builds) are exactly what Tasks is for — daari owns the executing process, so task state is local and survives client reconnects | [#289](https://github.com/naveenreddyalka/daari/issues/289) (P3) — SDK watch condition met |
| 11 | **Upgrade path doc** — no config-migration / version-upgrade guide for fleet operators | 3 | 2 | LiteLLM release notes discipline; [Kong ships kongctl migration tooling for AI Gateway 2.0](https://konghq.com/blog/product-releases/kong-ai-gateway-2-0-agentic-ai) | Fleet bootstrap exists; operators need "upgrade N→N+1 safely" | [#287](https://github.com/naveenreddyalka/daari/issues/287) (P2) |
| 12 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | [OpenRouter Image API (30+ models)](https://byteiota.com/openrouter-image-api-analytics-search-leaderboards/) | Local diffusion is a different product; only worth it if IDE clients start sending it | Non-goal for now |
| 13 | **MCP server-initiated events** — `2026-07-28` moved change notifications to an opt-in `subscriptions/listen` stream; daari's `/mcp` ingress has neither, and the [new MCP roadmap](https://blog.modelcontextprotocol.io/posts/mcp-roadmap/) makes server-initiated events + agent identity (DPoP/WIMSE) priority areas | 2 | 3 | MCP Tier-1 SDKs | List-changed notifications matter once daari fronts long-lived local tool servers; identity work is where enterprise MCP governance lands next | Watch — revisit when a daari-served client subscribes |

Open backlog after this run: [#269](https://github.com/naveenreddyalka/daari/issues/269)/[#270](https://github.com/naveenreddyalka/daari/issues/270)
implemented in stalled PRs #281/#283 (see Loop health); rows 1–5 filed as
#275–#279, plus [#285](https://github.com/naveenreddyalka/daari/issues/285)
(stall triage), [#287](https://github.com/naveenreddyalka/daari/issues/287)
(upgrade doc), [#288](https://github.com/naveenreddyalka/daari/issues/288)
(secret refs), [#289](https://github.com/naveenreddyalka/daari/issues/289)
(MCP Tasks) — all still unlabeled pending
[#286](https://github.com/naveenreddyalka/daari/issues/286). This run filed
only [#291](https://github.com/naveenreddyalka/daari/issues/291) (picker off
the search index, P1): with ten issues already queued behind a dead loop,
restocking the backlog is worth less than making the loop able to see it.

---

## Path to enterprise-grade — next 5 milestones

1. **Heterogeneous local inference** (row 1 + #269): any OpenAI-compat server as a
   local tier slot + agent prefix L1. Makes the org-GPU-pool topology real and keeps
   agent tokens on-device — the two claims enterprises actually buy.
2. **Streams that survive real networks** (row 2): keepalive on every SSE route
   (OpenAI, Anthropic, facade), so tunnels/LBs/IDEs never drop a cold-start stream.
3. **Governed tool plane** (row 3): per-key/team MCP tool policy + audit + spec
   headers — the Portkey/Kong "MCP gateway" pitch, but the tools run on the laptop.
4. **FinOps-grade attribution** (row 4): cost-split + savings headers joined with
   the existing per-team ledger; the "$ avoided" number goes on every response.
5. **Every IDE/desktop client one-click** (row 5): Claude Desktop recipe next to
   Cursor/Claude Code/JetBrains/VS Code; setup friction stays daari's moat.

Standing HITL asks: **unpark the dev loop first — both parks**
([#286](https://github.com/naveenreddyalka/daari/issues/286) human approvals +
labels, [#291](https://github.com/naveenreddyalka/daari/issues/291) picker off
the search index; every milestone above is gated on them); then PyPI/ghcr
publishing + image signing (row 8). License is Apache 2.0 (#227).

---

## Changelog

- **2026-08-30** — Found park #2: GitHub's search index for this repo went
  stale (2 of 14 open items indexed, zero label matches), and because
  `gh issue list --label` routes through GraphQL search, every scheduled
  `autodev-cycle` run since has no-oped with "backlog empty" — verified via
  `GH_DEBUG=api`; only `repository.issues(labels:)` returns truth. Filed
  [#291](https://github.com/naveenreddyalka/daari/issues/291) (P1) to move the
  picker + regression dedupe onto the repository connection (authorizes the
  minimal `autodev.yml` prompt edit). Only issue filed this run — ten are
  already queued behind the dead loop. Outward delta small: vLLM 0.28.0
  shipped (tiered KV offload, Model Runner V2); llama.cpp adopted semver
  (v0.3.0); Ollama 0.33.1/0.33.2 (MLX structured output, Claude Desktop proxy
  fix); LiteLLM stable still v1.98 (v1.99 RC: dark mode, CLI OAuth, batch
  billing, audit-on-by-default); Portkey still v2.18; Kong AI GW 2.1 still
  pending but its cost-analytics + budget-header docs are live (row 4 note);
  new MCP roadmap prioritizes server-initiated events + agent identity
  (added watch row 13).
- **2026-08-29** — Loop-health run. Found the dev loop parked: PRs #281/#283
  stalled on `action_required` CI approval, #275–#279 filed unlabeled (token
  cannot label/comment — 403s verified); filed HITL unblock
  [#286](https://github.com/naveenreddyalka/daari/issues/286) and stall-triage
  fix [#285](https://github.com/naveenreddyalka/daari/issues/285). Outward
  delta since 08-28: MCP Tasks Tier-1 SDK support shipped (watch condition met
  → filed [#289](https://github.com/naveenreddyalka/daari/issues/289)); A2A
  joined AAIF (governance only — keep watching); Kong AI Gateway 2.1 lands
  August with custom-model cost management (row 4 stays relevant); Kong
  shipped a Gemini streaming token double-count fix (checked daari: usage
  derives from one accumulated response, not summed chunks); vLLM late-Aug
  adds tiered KV-cache offload + Rust gRPC control plane; Ollama 0.33.2
  bugfix-only; LiteLLM stable still v1.98.0; Portkey v2.18 adds `/v1/ocr`.
  Converted watch rows 9/11 to issues
  [#288](https://github.com/naveenreddyalka/daari/issues/288)/[#287](https://github.com/naveenreddyalka/daari/issues/287).
- **2026-08-28** — First run. Created this PRD (renamed Phase-E spec to
  `phase-e-enterprise.md` to avoid macOS case collision). Outward scan: MCP
  `2026-07-28` stateless spec + Tasks/MRTR; A2A v1.0 (LF); Kong 3.14 A2A/MCP
  gateway + vLLM provider; LiteLLM v1.98 (cost headers, shadow evals, cosign);
  Portkey MCP Gateway GA + vault credentials; Ollama 0.33 Claude Desktop
  gateway; OpenRouter (now Stripe) Image/Analytics APIs; vLLM 0.27. Filed
  [#275](https://github.com/naveenreddyalka/daari/issues/275)–[#279](https://github.com/naveenreddyalka/daari/issues/279)
  covering rows 1–5.
