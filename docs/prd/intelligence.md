# daari — Prompt Intelligence & Transparency PRD

> **Status:** Shipped — released in v1.2.0 (features #19–#22; see [TRACKING.md](../TRACKING.md))
> **Last updated:** 2026-07-10
> **Companion to:** [PRD v0.4](PRD.md), [routing-spec](routing-spec.md)
> **Tracking:** GitHub issues labeled `auto-dev` (#19–#22); progress in [TRACKING.md](../TRACKING.md)

## Problem

daari routes well but understands shallowly and explains nothing:

1. **Shallow prompt understanding.** `Router._classify_task` is a keyword match with six buckets, used only for org-learning feedback. Category does not influence routing, caching, or escalation. There is no notion of prompt complexity, no token estimate, and no visibility into how close a prompt was to previously cached queries.
2. **No per-request audit trail.** `daari_meta` reports the final tier, but not the journey: which caches were checked, what similarity the nearest L1 entry had, why a tier was chosen, whether budget blocked escalation. Users (and their clients/customers) cannot see what daari did for a given prompt, so trust and debuggability suffer.
3. **Cache knowledge is wasted on near-misses.** When L1 similarity is just below the hit threshold (e.g. 0.80 vs 0.88), we discard the prior answer entirely and pay a full model generation — locally or, worse, at the frontier. The prior answer could seed the model as a draft to reformat/verify, cutting output tokens and latency.
4. **No token reduction.** Full message history is forwarded to local models every turn. Long Cursor sessions burn context window and latency on stale turns. There is no trimming, squeezing, or deduplication anywhere in the pipeline.

## Goals

- Every request gets a **prompt profile**: category, complexity, token estimate, nearest-cache similarity — computed locally in <5ms, no extra model calls.
- Category maps to a **configurable action policy** (initial tier, cache behavior) via settings; defaults preserve current behavior.
- Every request gets a **decision trace**: ordered steps with timings, persisted locally, retrievable by id via API/CLI, suitable for showing a customer exactly what daari did (`classified as code_gen; L0 miss; L1 nearest 0.81; policy chose L4; confidence 0.92; served locally, ~$0.0004 saved`).
- **Draft injection**: L1 near-misses (configurable band below the hit threshold) are attached as a draft answer for the serving model — including frontier escalations — with the trace recording that a draft was reused.
- **Context optimizer**: settings-driven history trimming + whitespace squeezing before local model calls, with saved chars recorded in trace and ledger.

## Non-goals

- No ML classifier model in this phase (heuristics only; the interface must allow swapping one in later).
- No UI dashboard changes beyond the existing endpoints (web-ui can consume the new endpoints later).
- No cross-request user analytics; traces are per-request and local-only, consistent with daari's privacy posture.

## Feature 1 — Prompt profile & category action policy (issue #19)

New module `daari/router/profile.py`:

```python
class PromptProfile(BaseModel):
    category: str          # code_gen | code_explain | test | git | lint | fetch | doc_qa | chat | tool
    complexity: str        # trivial | standard | complex
    prompt_tokens_est: int # chars/4
    l1_similarity: float | None  # nearest semantic-cache entry, even below threshold
```

- Categories extend `_classify_task`'s buckets with `code_gen` vs `code_explain` (imperative-verb + code-fence heuristics) and `doc_qa`.
- Complexity from token estimate + structural signals (code fences, multi-question, word count).
- `routing.category_policies` in settings: `{category: {tier: L3|L4|L5, cache: default|skip}}`. Unlisted categories fall through to existing weight-based tier choice.
- Profile fields surfaced in `daari_meta` (`task_type` = category, new `complexity`) and in the decision trace.

## Feature 2 — Decision trace (issue #20)

New module `daari/observability/trace.py`:

- `RequestTrace` accumulates ordered steps: `{step, detail, elapsed_ms}` — e.g. `profile`, `l0_lookup`, `l1_lookup` (with similarity), `policy`, `tier_attempt`, `fallback`, `escalate`, `budget_check`, `draft_injected`, `served`.
- `TraceStore` persists the last N traces (default 200, sqlite at `~/.daari/traces/traces.sqlite3`, settings `trace.*`).
- `daari_meta.trace_id` on every response; `GET /v1/daari/traces?limit=N` and `GET /v1/daari/traces/{id}`; `daari trace [id]` CLI for the client-facing story.
- Recording is best-effort and never fails the request path (same contract as the usage ledger).

## Feature 3 — Cached-draft injection (issue #21)

- New settings `cache.l1.draft_threshold` (default 0.75): near-miss band is `draft_threshold <= similarity < similarity_threshold`.
- `SemanticCache.get` gains a `nearest()` result (best entry + similarity regardless of threshold) so profile and draft logic share one lookup.
- On generation (local tiers and L6 escalation), a near-miss draft is appended as a system message: *"A previous answer to a similar question is below. Reuse whatever is still correct; reformat or correct as needed rather than writing from scratch."*
- Trace records `draft_injected` with the similarity; ledger unchanged (savings show up as fewer output tokens over time).

## Feature 4 — Context optimizer (issue #22)

- New settings block `context_optimizer`: `enabled` (default true), `max_history_messages` (default 20), `squeeze_whitespace` (default true).
- Applied to local-model requests only (never agent tool round-trips): keep all system messages + the most recent N non-system messages; collapse runs of >2 blank lines and trailing whitespace.
- Saved chars recorded as a trace step (`context_optimized`, chars_before/after) — visible evidence of token reduction per prompt.

## Rollout & validation

Each feature ships through the autonomous loop: failing tests first, implementation, default suite green in CI, auto-merge, then a live E2E cycle (`scripts/autodev-local.sh`: daemon restart on new main, live Ollama integration tests, Cursor-shaped smoke) — no manual testing required. Traces are validated E2E by making a live request and fetching its trace by id.

## Success metrics

- 100% of gateway requests carry `trace_id`; trace fetch by id returns the full step list.
- Category policy demonstrably changes initial tier for configured categories (test-pinned).
- Near-miss drafts injected when similarity is in band (test-pinned); frontier draft path covered by unit test.
- Context optimizer reduces forwarded chars on long histories (test-pinned) with zero behavior change for short ones.
