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

## Where daari stands (verified in-tree, 2026-09-09)

**The park is over and v1.4.0 shipped.** All nine held PRs merged on 09-08
(#340, #347–#350, #360–#363, plus the auto-drain fix
[#372](https://github.com/naveenreddyalka/daari/pull/372) and Redis alert
dedupe [#371](https://github.com/naveenreddyalka/daari/pull/371)), the human
tagged and released **v1.4.0** the same evening, and every stall-tracker issue
closed. The backlog was completely empty at the start of this run — refilled
with five issues below. Loop plumbing hardened: `autodev_pr_watch.py` now
merges `origin/main` into `BEHIND` auto-merge PRs and approves first-party
held runs; `autodev.yml` prefers an `AUTODEV_GH_TOKEN` PAT so future bot PRs
skip GitHub's 2026-06-11 approval gate (secret not yet set — HITL below).

Shipped surface (see 08-28→09-08 scans for provenance): Apache 2.0
([ADR-0016](../adr/0016-apache-2-relicense.md)), virtual keys + multi-window
budgets (opt-in rollover) + teams + per-key RPM/TPM + **global in-flight cap
with queue and 503 + Retry-After (#169)** + key/SSO expiry, SSO/OIDC +
IdP-minted keys, RBAC, append-only audit with `list`/JSONL export,
retention/prune, policy sync, fleet bootstrap, Redis L0/L1 + Postgres
ledger/traces, Helm + Grafana, Prometheus + OTel GenAI, budget headers +
threshold webhooks (Redis-deduped across replicas), guardrails + PII scrub
(chat + MCP ingress/egress + per-key/team tool governance), MCP ingress
(2026-07-28, Tasks) + egress with full `nextCursor` pagination, `secret://`
refs incl. OAuth client-credentials, Responses API, `/v1/embeddings`, Ollama
facade incl. `/api/generate`+`/api/embed` (ChatGPT Desktop recipe),
OpenAI-compat local backends (vLLM/llama.cpp/LM Studio), OpenRouter
`provider` object, September-2026 frontier pricing + capabilities, session
affinity, stall escalation, context-length failover + compression, circuit
breakers, signed images + SBOM, shadow evals. Proof: 1555 mocked tests;
published load (320 rps L0 / 61 ms p95), vs-LiteLLM, cost-of-pass pages.

**Positioning:** Portkey is the PANW Prisma AIRS AI Gateway (public changelog
quiet since April). Kong AI Gateway quiet (2.0.3, 08-31). LiteLLM shipped
**v1.101.0 stable** (heuristic/hybrid auto-router, semantic MCP tool search,
off-peak pricing, per-worker admission control — routing customization still
metered behind the `auto_router` enterprise license) and its v1.102-dev line
adds **post_call guardrails on streaming responses**. daari's counter-pitch
is unchanged: routing *is* the Apache 2.0 core, run-it-yourself, tokens never
leave the building — and the 09-09 refill targets exactly the three fronts
LiteLLM is monetizing (phase routing, stream guardrails, tool search).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Subtask/phase routing** — no per-agent-phase tiering (explore/verify/implement); LiteLLM's 09-07 experiment matched fixed-Opus quality at 46% less cost; session affinity + stall escalation (the groundwork) merged 09-08 | 4 | 3 | [LiteLLM subtask classifier](https://docs.litellm.ai/blog/subtask-type-routing) (experimental, enterprise-licensed) | Phase detection from tool history is stateless and on-box; explore turns are exactly what $0 local tiers are for | **Done [#374](https://github.com/naveenreddyalka/daari/issues/374)** |
| 2 | **Guardrails force full stream buffering** — `_can_relay_frontier_stream` returns False with guardrails on; every streamed answer buffers before the first byte (verified `router.py` ~3127) | 4 | 3 | [LiteLLM v1.102-dev streaming post_call guardrails](https://github.com/BerriAI/litellm/pull/38788) | Rules are regex + local PII scrub — incremental scanning is microseconds per chunk, no guardrail API hop | **Done [#375](https://github.com/naveenreddyalka/daari/issues/375)** |
| 3 | **MCP semantic tool search** — pagination (#363) means aggregated catalogs of hundreds of tools now reach small local models, which are most hurt by tool flooding | 4 | 3 | LiteLLM `mcp_tool_search` (v1.101 stable, embedding-ranked) | `/v1/embeddings` + local embed models → $0 ranking, tool descriptions never leave the box | **Filed [#376](https://github.com/naveenreddyalka/daari/issues/376)** (P2) |
| 4 | **No zero-downtime key rotation** — revoke+create is a hard cutover losing budgets/team/policy identity; SOC 2-style rotation schedules expect overlap | 3 | 2 | LiteLLM key regenerate | Rotation is a local state transition + audit row; completes the on-box credential lifecycle with expiry (#331) | **Filed [#377](https://github.com/naveenreddyalka/daari/issues/377)** (P2) |
| 5 | **Audit log is not tamper-evident** — SQLite rows editable by anyone with disk access; export shows no trace | 3 | 2 | Nobody (LiteLLM/Kong audit is plain DB rows) | Self-hosted audit needs tamper-evidence *more* than SaaS; SHA-256 hash chain is stdlib-only | **Done [#378](https://github.com/naveenreddyalka/daari/issues/378)** |
| 6 | **Batch API** — no `/v1/batches`; agents and eval pipelines increasingly submit batch jobs | 4 | 4 | OpenRouter Batch API (beta); LiteLLM e2e batch billing | Drain batches through idle local tiers overnight at $0 — no cloud gateway can copy it. MCP Tasks store (#315) is the template | Watch — file when a daari-served client sends batches; sketch first |
| 7 | **MCP agent identity** — [WIF SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) + DPoP SEP-1932 both still **draft** (re-checked 09-09); MCP roadmap makes agent identity a priority area | 3 | 3 | MCP Tier-1 SDKs; LiteLLM MCP session RFC 7662 + ID-JAG relay | Workload JWTs (K8s/SPIFFE) as inbound auth fit fleets; `secret://oauth` + key expiry are the groundwork | Watch — file when SEP-1933 merges or a fleet asks |
| 8 | **Gemini-native facade** — no `/v1beta` `generateContent`; Gemini CLI can't point at daari | 3 | 4 | Nobody self-hosted | Same dialect-facade trick as Ollama/Anthropic | Watch — file when a target client is confirmed |
| 9 | **A2A gateway** — no Agent2Agent ingress/egress governance | 3 | 4 | Kong Agent Gateway | Local agents delegating over A2A get routing/cache/policy without a cloud hop | Watch — revisit when a daari-served client speaks A2A |
| 10 | **Admin console** — web dashboard read-only; key/team/budget management is CLI-only | 3 | 4 | LiteLLM admin UI | CLI-first fits operators; a UI matters at org rollout scale | Watch — wait for operator demand |
| 11 | **Off-peak pricing windows** — some providers discount by time window; daari prices flat per model | 2 | 2 | LiteLLM `off_peak_pricing` (v1.101 stable) | Local math at cost time; pairs with rollover (#349) | Watch — file when a provider daari routes to publishes off-peak rates |
| 12 | **Per-request `cost_tier` body param** — OpenRouter Auto router GA'd it in-body; daari has `X-Daari-Tier-Cap` header + profiles | 2 | 2 | OpenRouter Auto router | Header + `.daari.yaml` cover most cases | Watch — file if a client can't set headers |
| 13 | **Streamed live cost** — LiteLLM puts `usage.cost` on the final streamed usage chunk; daari streams a usage chunk without cost (cost headers can't carry a post-stream figure) | 2 | 2 | LiteLLM spend controls | Cost math is already local (#278); one field on the existing usage chunk | Watch — file when a streaming client asks for live spend |
| 14 | **Ollama 0.34 facade parity** — 0.34 (rc3) adds OpenAI-compat client tool search and response compaction; daari's facade tolerates unknown fields (`extra="ignore"`) but hasn't been verified against the GA surface | 2 | 2 | Ollama upstream | Facade recipe is daari's ChatGPT Desktop path (#343) | Watch — verify `/api` parity when 0.34.0 GAs |
| 15 | **Image/multimodal generation API** — chat vision routes; no `/v1/images` | 2 | 4 | OpenRouter Image API | Local diffusion is a different product | Non-goal for now |

Open backlog after this run:
[#376](https://github.com/naveenreddyalka/daari/issues/376) MCP
tool search, [#377](https://github.com/naveenreddyalka/daari/issues/377) key
rotation — remaining open P2 while #378 ships.

---

## Path to enterprise-grade — next 5 milestones

1. **Ship the routing/guardrail counter-offensive** (rows 1–3,
   [#374](https://github.com/naveenreddyalka/daari/issues/374)–[#376](https://github.com/naveenreddyalka/daari/issues/376)):
   phase routing, incremental stream guardrails, and semantic tool search are
   the three features LiteLLM is monetizing behind its enterprise license —
   daari ships them Apache 2.0, on-box, at $0 marginal cost.
2. **Complete the credential lifecycle** (rows 4–5,
   [#377](https://github.com/naveenreddyalka/daari/issues/377)/[#378](https://github.com/naveenreddyalka/daari/issues/378)):
   zero-downtime rotation and tamper-evident audit close the two remaining
   SOC 2-shaped holes in the keys/audit story.
3. **End the approval-gate class for good** (HITL): set the
   `AUTODEV_GH_TOKEN` secret (a user PAT) so autodev PRs stop being
   `github-actions[bot]`-attributed; merge the green release-chore PR
   [#373](https://github.com/naveenreddyalka/daari/pull/373) (brew formula
   for v1.4.0).
4. **Batch API when demand lands** (row 6): idle local tiers overnight at $0
   is the single most defensible cost story daari hasn't told yet.
5. **Agent identity when the spec settles** (row 7): SEP-1933 is a named MCP
   roadmap priority; `secret://oauth` and key expiry mean daari can move
   within days of the merge.

Standing HITL asks: set `AUTODEV_GH_TOKEN` (repo secret, user PAT with
contents+PR scope); merge [#373](https://github.com/naveenreddyalka/daari/pull/373)
(all checks green; brew formula for the v1.4.0 release you tagged).

---

## Changelog

- **2026-09-09** — **Park over, v1.4.0 released, backlog refilled.** All nine
  held PRs merged 09-08 plus auto-drain (#372) and alert dedupe (#371); human
  tagged v1.4.0. Backlog was empty — filed
  [#374](https://github.com/naveenreddyalka/daari/issues/374) phase routing,
  [#375](https://github.com/naveenreddyalka/daari/issues/375) incremental
  streaming guardrails (verified: guardrails currently disable the stream
  relay and force full buffering),
  [#376](https://github.com/naveenreddyalka/daari/issues/376) MCP semantic
  tool search, [#377](https://github.com/naveenreddyalka/daari/issues/377)
  key rotation, [#378](https://github.com/naveenreddyalka/daari/issues/378)
  audit hash chain (all P2). Outward: LiteLLM v1.101.0 stable + v1.102-dev
  streaming guardrails; vLLM v0.29.0 (MRV2 default, queue admission flags);
  Ollama 0.34.0-rc3 (ChatGPT Desktop, new watch row 14); Kong quiet;
  SEP-1933 still draft; OpenRouter GA'd Responses + `cost_tier`. Inward
  corrections: **global in-flight cap already shipped** (#169 — admission
  row pruned); Anthropic gateway accepts unknown content blocks (no parity
  defect). New HITL: set `AUTODEV_GH_TOKEN`, merge #373.
- **2026-09-08** — Park deepened to nine PRs (fifth day). Named the drain
  hazard (strict up-to-date protection ⇒ ~9 manual rounds). Filed #368
  auto-drain + #369 alert dedupe; stopped at 2/5 issues deliberately.
  Outward: LiteLLM subtask/phase routing blog (09-07), stall-escalation post.
- **2026-09-07** — Full park (five PRs). LiteLLM v1.101-rc.1 routing
  offensive behind `auto_router` license; Fable 5.1 + GPT-6 Astra at $10/$50.
  Filed #355 pricing (P1), #356 session affinity, #357 stall escalation,
  #358 MCP pagination.
- **2026-09-06** — Label HITL ended (labeler #336). One park (#340); stall
  re-pick spam → #342 dedupe, #343 ChatGPT Desktop facade, #344 budget
  rollover, #345 audit read path.
- **2026-09-03** — Second drain in two days. Refill: #330 labeler, #331 key
  expiry, #332 retention, #333 budget webhooks, #334 v1.4.0 prep.
- **2026-09-02** — Backlog drained; Apache 2.0 merged; 15 PRs in ~36h.
- **2026-08-28→09-01** (condensed) — Created this PRD; discovered the
  `action_required` park class, the stale search index (→ GraphQL reads), the
  closing-keyword hazard, the PANW/Portkey acquisition; filed #275–#279,
  #285–#289, #294–#297.
