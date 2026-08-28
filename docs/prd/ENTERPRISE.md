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

**Adoption blockers that are HITL, not eng:** PolyForm NC license requires a
commercial license for any business use
([#227](https://github.com/naveenreddyalka/daari/issues/227)) — until resolved,
"enterprises run daari instead of LiteLLM (MIT)" is legally gated, whatever we
ship. PyPI/ghcr publishing stays user-gated.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **OpenAI-compat local backend kind** — local tiers only speak Ollama/MLX; no first-class vLLM / llama.cpp server / LM Studio / SGLang slot | 5 | 2 | [Kong 3.14 added vLLM provider](https://konghq.com/blog/product-releases/kong-ai-gateway-3-14); LiteLLM 100+ providers | Enterprises standardize GPU pools on vLLM; daari's gateway-heavy topology (ROADMAP-v2 F4) is fiction without it. Pool/breaker plumbing (#170) already abstracts slots | Issue filed (P1) |
| 2 | **SSE keepalive heartbeat** — no ping on streaming routes; cold model loads (30s+) send zero bytes and LBs/tunnels/IDEs time out | 4 | 1 | [LiteLLM v1.98 global + per-deployment keepalive](https://docs.litellm.ai/release_notes/) | daari sits behind cloudflared tunnels (Cursor BYOK) where idle timeouts are the default failure; local cold-start is our worst case, not theirs | Issue filed (P1) |
| 3 | **MCP tool governance** — `/mcp` ingress + egress have no per-key/team tool allow/deny, no audit rows, no `Mcp-Method`/`Mcp-Name` headers | 4 | 2 | [Portkey MCP Gateway GA](https://portkey.ai/docs/changelog/2026/january) (registry, RBAC per tool, logs); Kong MCP gateway | Tool calls carry the most sensitive payloads; governing them on-device beats shipping them to a hosted gateway. RBAC/audit/policy modules already exist to wire in | Issue filed (P2) |
| 4 | **Cost-split response headers** — `daari_meta` has cost but no header contract FinOps tooling can scrape per response | 3 | 1 | [LiteLLM `x-litellm-response-cost-*`](https://docs.litellm.ai/release_notes/) (input/cache/output/reasoning split) | daari can also report **$ avoided** (frontier-implied vs $0 local) per response — a number no proxy can honestly print | Issue filed (P2) |
| 5 | **Claude Desktop one-click** — Ollama 0.33 made Claude Desktop a third-party-gateway client; daari has no recipe | 3 | 2 | [Ollama 0.33](https://github.com/ollama/ollama/releases/tag/v0.33.0) | daari already ships an Ollama facade + recipe framework; pointing Claude Desktop at daari adds cache/routing/budgets Ollama alone lacks | Issue filed (P2) |
| 6 | **A2A v1.0 gateway** — no Agent2Agent support (ingress agent card or egress governance) | 3 | 4 | [Kong Agent Gateway GA](https://konghq.com/blog/product-releases/kong-agent-gateway); A2A v1.0 under Linux Foundation, 150+ orgs | Local agents delegating over A2A would get routing/cache/policy without a cloud hop | Watch — revisit when a client daari serves speaks A2A |
| 7 | **Router shadow evals** — no way to measure "would L6 have answered differently" on sampled live traffic before trusting a threshold change | 3 | 3 | [LiteLLM v1.98 auto-router shadow evals](https://docs.litellm.ai/release_notes/v1.98.0/v1-98-0) | daari already shadow-samples cache hits (false-hit rate); extending to tier decisions makes learned routing auditable | Backlog next run if #269 lands |
| 8 | **Signed images + SBOM** — ghcr image unsigned, no SBOM/provenance | 3 | 2 | LiteLLM signs with cosign (v1.97+) | Table stakes for enterprise supply-chain review | Needs an issue that explicitly authorizes the workflow edit (AGENTS.md hard limit) |
| 9 | **Secret references / vault-backed keys** — frontier + org keys live in env/config | 3 | 3 | [Portkey vault-backed credentials](https://portkey.ai/docs/changelog/2026/march.md) | Keys never leave the machine today; a local keyring/vault ref keeps that story while passing security review | Backlog |
| 10 | **MCP 2026-07-28 depth** — version negotiated, but Tasks extension (long-running `tools/call`) and MRTR not implemented; Lt commands block the call | 2 | 3 | Cloudflare/New Relic stateless MCP writeups; [spec blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/) | Long local commands (test suites, builds) are exactly what Tasks is for | Watch — adopt when client SDKs stabilize |
| 11 | **Upgrade path doc** — no config-migration / version-upgrade guide for fleet operators | 3 | 2 | LiteLLM release notes discipline | Fleet bootstrap exists; operators need "upgrade N→N+1 safely" | Backlog next run |
| 12 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | [OpenRouter Image API (30+ models)](https://byteiota.com/openrouter-image-api-analytics-search-leaderboards/) | Local diffusion is a different product; only worth it if IDE clients start sending it | Non-goal for now |

Open `auto-dev` backlog before this run: [#269](https://github.com/naveenreddyalka/daari/issues/269)
(G1b agent prefix L1, P1), [#270](https://github.com/naveenreddyalka/daari/issues/270)
(service install `--now`, P2) — both still the right next cards alongside rows 1–5.

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

Standing HITL asks: resolve licensing (#227); then PyPI/ghcr publishing + image
signing (row 8).

---

## Changelog

- **2026-08-28** — First run. Created this PRD (renamed Phase-E spec to
  `phase-e-enterprise.md` to avoid macOS case collision). Outward scan: MCP
  `2026-07-28` stateless spec + Tasks/MRTR; A2A v1.0 (LF); Kong 3.14 A2A/MCP
  gateway + vLLM provider; LiteLLM v1.98 (cost headers, shadow evals, cosign);
  Portkey MCP Gateway GA + vault credentials; Ollama 0.33 Claude Desktop
  gateway; OpenRouter (now Stripe) Image/Analytics APIs; vLLM 0.27. Filed 5
  issues covering rows 1–5.
