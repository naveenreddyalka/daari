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

## Where daari stands (verified in-tree, 2026-09-06)

**The label HITL is over.** The 09-03 refill (#330–#333) shipped the same day:
issue auto-labeler workflow ([#336](https://github.com/naveenreddyalka/daari/pull/336)),
virtual key + SSO credential expiry ([#337](https://github.com/naveenreddyalka/daari/pull/337)),
retention windows + `daari prune` ([#338](https://github.com/naveenreddyalka/daari/pull/338)),
and budget threshold webhooks ([#339](https://github.com/naveenreddyalka/daari/pull/339)).
This run's four issues were auto-labeled within seconds of filing — no human
label step remains in the loop.

**One park:** PR [#340](https://github.com/naveenreddyalka/daari/pull/340)
(v1.4.0 release-notes prep, closes #334) is `BLOCKED` — its CI run concluded
`action_required` and the agent token cannot approve held runs. The stall
watcher filed [#341](https://github.com/naveenreddyalka/daari/issues/341), and
the cycle then re-picked #341 ~a dozen times, posting duplicate blocked
comments — that loop defect is now [#342](https://github.com/naveenreddyalka/daari/issues/342).
Human fix: **Approve and run** on
[run 33815553913](https://github.com/naveenreddyalka/daari/actions/runs/33815553913),
then tag v1.4.0 once #340 merges.

Longer-standing surface (see 08-28→09-03 scans): Apache 2.0
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
signed images + SBOM. Proof: 1141+ mocked tests; published load (320 rps L0 /
61 ms p95), vs-LiteLLM, cost-of-pass pages.

**Positioning (unchanged):** Palo Alto Networks
[acquired Portkey](https://www.paloaltonetworks.com/company/press/2026/palo-alto-networks-completes-acquisition-of-portkey-to-secure-ai-agents)
(now the Prisma AIRS AI Gateway; public product changelog quiet since April) —
developer-first/self-hosted buyers face roadmap uncertainty there. daari's
counter-pitch: Apache 2.0, run-it-yourself, tokens never leave the building.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Stall re-pick spam** — a human-gated stall issue (#341) gets re-picked every cycle; ~12 duplicate blocked comments in 3 days, every scheduled run wasted while parked | 4 | 1 | n/a (loop health) | Parked time should cost nothing; one blocked comment per distinct blocked state, then skip until PR state changes | [#342](https://github.com/naveenreddyalka/daari/issues/342) (P1) |
| 2 | **ChatGPT Desktop as a client** — Ollama v0.34 lets ChatGPT Desktop run local models via Ollama; daari's facade lacks `/api/generate` + `/api/embed` and has no recipe | 4 | 2 | [Ollama v0.34.0-rc1](https://github.com/ollama/ollama/releases/tag/v0.34.0-rc1) (direct, ungoverned) | The highest-distribution desktop AI app hard-wired to localhost Ollama — only a local facade can front it with cache/routing/budgets/traces; same trick as the JetBrains facade | [#343](https://github.com/naveenreddyalka/daari/issues/343) (P2) |
| 3 | **Budget rollover** — unused window headroom evaporates at reset; LiteLLM v1.100 **stable** ships opt-in rollover as a headline (watch condition met) | 3 | 2 | [LiteLLM v1.100.0](https://docs.litellm.ai/release_notes/v1.100.0/v1-100-0) | Budget state lives on the operator's box; rollover is local math at reset, and #319/#327 headers + #333 webhooks reflect it for free | [#344](https://github.com/naveenreddyalka/daari/issues/344) (P2) |
| 4 | **Audit read path** — audit rows are written (keys, MCP governance, budget alerts, prune) but there is no CLI or export; compliance answer today is "open the SQLite file" | 3 | 1 | [LiteLLM audit default-on + UI](https://docs.litellm.ai/release_notes/v1.99.0/v1-99-0); [Portkey log export w/ field restrictions](https://portkey.ai/docs/changelog/backend) | The trail never left the box — export is a local file read, no vendor data processor; closes record → retain (#332) → **review/export** | [#345](https://github.com/naveenreddyalka/daari/issues/345) (P2) |
| 5 | **v1.4.0 unshipped** — prep PR #340 done but held on manual CI approval; pyproject + last tag still v1.3.0 while main holds relicense, signed images, MCP governance, FinOps loop | 3 | 1 | n/a (distribution) | First release a company can legally adopt (Apache 2.0) and verify (cosign) | HITL: approve [run 33815553913](https://github.com/naveenreddyalka/daari/actions/runs/33815553913), let #340 merge (issue #334), then tag |
| 6 | **Batch API** — no `/v1/batches`; agents and eval pipelines increasingly submit batch jobs | 4 | 4 | [OpenRouter Batch API (beta)](https://openrouter.ai/docs); LiteLLM e2e batch billing | Drain batches through idle local tiers overnight at $0 — no cloud gateway can copy it. MCP Tasks store (#315) is the template | File when a daari-served client sends batches; sketch first |
| 7 | **Gemini-native facade** — no `/v1beta` `generateContent`; Gemini CLI and Gemini-native SDK agents cannot point at daari | 3 | 4 | Nobody self-hosted; OpenRouter translates server-side | Same dialect-facade trick as Ollama/Anthropic | Watch — file when a target client is confirmed |
| 8 | **MCP agent identity + server events** — roadmap now names [WIF (SEP-1933)](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) + DPoP (SEP-1932) + ID-JAG; LiteLLM v1.100 added RFC 7662 introspection for MCP session tokens | 3 | 3 | MCP Tier-1 SDKs; LiteLLM MCP session hardening | Workload JWTs (K8s/SPIFFE) as inbound auth fit fleets that already resent pasted keys; `secret://oauth` (#329) + key expiry (#337) are the groundwork | Watch — file when SEP-1933 merges to spec or a fleet asks |
| 9 | **A2A gateway** — no Agent2Agent ingress card or egress governance | 3 | 4 | [Kong Agent Gateway](https://konghq.com/blog/product-releases/kong-agent-gateway); A2A under AAIF | Local agents delegating over A2A would get routing/cache/policy without a cloud hop | Watch — revisit when a client daari serves speaks A2A |
| 10 | **Admin console for keys/teams/budgets** — web dashboard read-only; management is CLI-only | 3 | 4 | LiteLLM admin UI (key management end-to-end) | CLI-first fits operators; a UI matters at org rollout scale | Watch — wait for operator demand |
| 11 | **Per-request cost/quality hint in body** — OpenRouter's new Auto router takes `cost_tier` (low→max) in the request; daari has `X-Daari-Tier-Cap` header + project profiles, no body param | 2 | 2 | [OpenRouter Auto router](https://openrouter.ai/blog/announcements/introducing-the-new-auto-router/) | Header + `.daari.yaml` cover most cases; body-param parity is polish for SDKs that can't set headers | Watch — file if a client integration hits the header limitation |
| 12 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API | Local diffusion is a different product | Non-goal for now |

Open backlog after this run:
[#342](https://github.com/naveenreddyalka/daari/issues/342) (stall re-pick, P1),
[#343](https://github.com/naveenreddyalka/daari/issues/343) (ChatGPT Desktop facade, P2),
[#344](https://github.com/naveenreddyalka/daari/issues/344) (budget rollover, P2),
[#345](https://github.com/naveenreddyalka/daari/issues/345) (audit export, P2) —
all auto-labeled at filing; plus human-gated
[#334](https://github.com/naveenreddyalka/daari/issues/334)/[#341](https://github.com/naveenreddyalka/daari/issues/341)
(PR #340 approval).

---

## Path to enterprise-grade — next 5 milestones

1. **Unpark and ship v1.4.0** (row 5, HITL + #334): one human click on the held
   CI run merges #340; then tag. First Apache-2.0, cosign-verifiable release —
   distribution is the bottleneck, not features.
2. **Make parked time free** (row 1, #342): a human-gated stall should cost
   one comment, not every scheduled run. Protects the loop's economics for
   every future hold.
3. **Win the desktop client beachhead** (row 2, #343): ChatGPT Desktop via the
   Ollama facade + `/api/generate`/`/api/embed` completes facade coverage and
   adds the largest-distribution client daari can serve.
4. **FinOps completeness** (rows 3–4, #344/#345): rollover makes tight budgets
   honest; the audit read path turns "we log admin actions" into a compliance
   answer with a SIEM-ready export.
5. **Agent-identity groundwork** (row 8, watch): when SEP-1933/WIF lands,
   accept workload JWTs inbound — key expiry (#337) and `secret://oauth`
   (#329) already put daari ahead of the curve here.

Standing HITL asks: **approve CI run
[33815553913](https://github.com/naveenreddyalka/daari/actions/runs/33815553913)**
(unblocks #340 → #334 → v1.4.0), then **tag + release v1.4.0** (agent cannot
tag/publish). Consider relaxing the Actions approval policy for bot-authored
PRs — this is the third `action_required` park.

---

## Changelog

- **2026-09-06** — **Label HITL ended:** #330–#333 shipped 09-03 (labeler,
  key expiry, retention, budget webhooks); this run's issues self-labeled in
  seconds. One park: PR #340 (v1.4.0 prep) held on manual CI approval; the
  cycle re-picked stall issue #341 ~12 times with duplicate comments → filed
  [#342](https://github.com/naveenreddyalka/daari/issues/342) (stall re-pick
  dedupe, P1). Outward: **Ollama v0.34.0-rc1** (ChatGPT Desktop runs local
  models via Ollama → [#343](https://github.com/naveenreddyalka/daari/issues/343)
  facade recipe + `/api/generate`/`/api/embed`); **LiteLLM v1.100.0 stable**
  (budget rollover headline → watch row condition met →
  [#344](https://github.com/naveenreddyalka/daari/issues/344); MCP session
  RFC 7662 introspection + RS256 → row 8 note; spend-logs read cap — daari's
  trace/ledger reads verified already bounded); **MCP roadmap** centers WIF
  SEP-1933 + DPoP SEP-1932 (row 8); **OpenRouter** market-data Auto router
  with `cost_tier` body param (new watch row 11; daari's header + profiles
  cover it). Audit read-path gap verified in-tree (no CLI/export) →
  [#345](https://github.com/naveenreddyalka/daari/issues/345). Four shipped
  rows pruned; Kong quiet (2.0.3); Portkey enterprise still v2.20.
- **2026-09-03** — Second full drain in two days: #317–#321 shipped overnight
  (PRs #324–#329). Refill: #330 auto-labeler, #331 key expiry, #332
  retention, #333 budget webhooks, #334 v1.4.0 prep. New rows: batch API,
  rollover watch, Gemini facade watch.
- **2026-09-02** — Backlog drained; table rebuilt. Human unparked both parks
  and merged #293 (Apache 2.0); loop shipped 15 PRs in ~36h (#299–#316).
  Refiled: #317 MCP tool guardrails, #318 shadow evals, #319 budget headers,
  #320 streaming-usage pin, #321 `secret://oauth`. Outward: Kong AI GW 2.0 GA,
  Portkey v2.20 (MCP guardrails, WIF), LiteLLM v1.99 stable.
- **2026-09-01** — Relicense PR #293 went `DIRTY`; recorded the Palo Alto
  Networks/Portkey acquisition fact; filed #297 (`reasoning_effort` dropped —
  shipped next day as #312).
- **2026-08-31** — Human opened Apache 2.0 relicense PR #293. Found #285
  auto-closed by a PRD PR closing keyword → re-filed as #294; standing rule:
  no closing keywords in PRD PR bodies. Converted row 8 → #295 (cosign+SBOM).
- **2026-08-30** — Found park #2: GitHub search index stale; filed #291
  (picker onto GraphQL). MCP roadmap → watch row.
- **2026-08-29** — Found park #1: PRs stalled on `action_required`, issues
  unlabeled (token 403) → filed #285/#286 (HITL unblock), #287–#289.
- **2026-08-28** — First run. Created this PRD; filed #275–#279.
