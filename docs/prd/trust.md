# daari — Trust & Efficiency PRD

> **Status:** Active — Train 1 in progress
> **Last updated:** 2026-07-12
> **Companion to:** [PRD v0.4](PRD.md), [intelligence PRD](intelligence.md), [learning PRD](learning.md)
> **Tracking:** GitHub issues labeled `auto-dev`; progress in [TRACKING.md](../TRACKING.md)

## Why this PRD

Competitive research (Portkey, LiteLLM, OpenRouter, Requesty, RouteLLM,
GPTCache/vCache postmortems, SmarterRouter and other local-first routers)
surfaced the documented user pain in this space, in order:

1. **Semantic caches serve confidently wrong answers silently.** Production
   postmortems report 3–7% of hits wrong at useful thresholds, and one case
   where 95% of hits were false positives caused by template-heavy inputs.
   Everyone dashboards hit rate; nobody measures false-hit rate.
2. **Slow local models blow interactive latency** with no budget mechanism.
3. **Budget surprises** — a single hard daily cap is not enough.
4. **Template/boilerplate inputs poison embedding similarity.**
5. Frontier prompt caching and context compaction are the biggest untouched
   token-cost levers.

daari already has tiered routing, L0/L1 with TTLs, draft injection, category
policies, confidence escalation with a tuner, feedback/outcome stores, a
fine-tuning pipeline, traces, a savings ledger, and a frontier budget guard.
This PRD covers what is genuinely missing, as five loop trains.

---

## Train 1 — Cache trust (highest UX impact)

### T1a — Embedding input normalization

- New `normalize_for_embedding(text)` applied before every L1 embed (both
  put and lookup): squeeze whitespace, strip markdown code fences and JSON
  scaffolding (braces/keys boilerplate), drop leading role/instruction
  boilerplate lines that repeat across requests.
- Cache keys and stored answers are unchanged — only the *embedded* text is
  normalized, so similarity reflects intent, not shared template bytes.
- Setting `cache.l1.normalize_inputs` (default **true**).

### T1b — Response-diversity monitor

- `SemanticCache.diversity_stats()`: per stored category, unique-answer
  count vs entry count; a category serving 1 unique answer across many
  entries is the canonical broken-cache signal.
- Surfaced in `GET /v1/daari/cache/diversity` + `daari cache stats`
  extension; `daari doctor` warns when a category's unique-answer ratio
  drops below 0.5 with ≥ 10 entries.

### T1c — Shadow sampling + false-hit rate

- `cache.l1.shadow_sample_rate` (default 0.05): that fraction of L1 hits
  also runs the local model in the background after the response is served
  (never blocking the client), embeds both answers, and records a
  `shadow_check` row (category, similarity of answers, verdict) via the
  feedback store.
- False-hit rate per category = disagreeing shadow checks / sampled hits,
  exposed in `daari learn stats` and `GET /v1/daari/learn/stats`.
- The routing tuner consumes it: categories with false-hit rate above 10%
  get their L1 similarity threshold raised one notch (+0.02, bounded at
  0.99) — evidence-gated like the confidence tuner.

### T1d — Report and dashboard panel

- `daari report` and the web dashboard show L1 hit rate *and* false-hit
  rate per category — the number competitors don't show.

---

## Train 2 — Deeper token savings

### T2a — Provider prompt-cache passthrough on L6

- Anthropic escalations mark the stable system prefix with `cache_control`
  (ephemeral); OpenAI caching is automatic on stable prefixes.
- Frontier slimming must keep the prefix byte-stable across requests
  (never reorder/rewrite system messages); pin with tests.
- Trace step `prompt_cache_hint` with marked block count.

### T2b — Conversation compaction

- Upgrade the trim-only context optimizer: when history exceeds
  `context_optimizer.max_history_messages`, old turns are summarized by L3
  into one pinned `[Earlier conversation summary]` system message instead
  of being dropped. Summaries are cached per conversation prefix (L0 keying)
  so compaction itself doesn't burn tokens repeatedly.
- Setting `context_optimizer.compact` (default false initially).

### T2c — Frontier compression (LLMLingua-lite)

- Optional `frontier.compress_context` (default false): before L6, long
  non-system messages are pruned sentence-wise by relevance to the last
  user message (embedding ranking with the existing Ollama embedder — no
  new deps), targeting `frontier.compress_target_ratio` (default 0.6).
- Traced with before/after character counts; never applied to tool flows.

---

## Train 3 — Latency-aware routing

### T3a — Model profiling

- `daari profile` benchmarks each installed local model (short fixed
  prompt): tokens/sec, wall latency, load time; stores to
  `~/.daari/profile/models.json`; `daari profile --show` prints it.

### T3b — Latency budgets

- `routing.latency_budget_ms` (global), per-category override in
  `category_policies.latency_budget_ms`, and `X-Daari-Latency-Budget`
  header (header wins).
- Router consults the profile: if the chosen tier's expected latency
  exceeds the budget, step down to a faster local tier; trace step
  `latency_budget` records expected vs budget and the downgrade.

### T3c — Warm-model awareness

- Query Ollama `/api/ps` (cached ~5s): when tier choice is otherwise tied
  (weight-based path), prefer the loaded model to avoid cold-load stalls;
  trace records `warm=true/false`.

---

## Train 4 — Learned routing (our D1 data moat)

- `daari learn train-router`: fits a tiny centroid-based classifier
  (embeddings of past prompts from the example store + categories/outcomes
  from the feedback store — no new deps) and stores it locally.
- At request time, if a trained router exists and
  `routing.learned_router` is true, category and initial tier come from
  the classifier when its confidence clears a floor; otherwise heuristics.
  Trace step `learned_route` with confidence.
- Falls back automatically below `learning.router_min_samples` (default
  200) — never guesses from thin data.

---

## Train 5 — Budget & client UX

### T5a — Soft/hard budgets

- `frontier.daily_budget_usd` gains `frontier.monthly_budget_usd` and
  `frontier.soft_budget_ratio` (default 0.8): crossing the soft line adds
  `daari_meta.warning="frontier_budget_warning"` (still serves); crossing
  the hard line behaves as today (local-only). Both in `daari report`.

### T5b — Per-client attribution

- The ledger records `client_id` (existing header) per row; `daari report
  --by-client` and the report endpoint group usage/savings per client.

### T5c — Pre-L6 PII scrub

- `frontier.scrub_pii` (default false): before any L6 escalation, regex
  scrub of emails, phone numbers, SSNs, credit cards, IPs → typed
  placeholders (`<email-1>`). Applied only to the outbound L6 copy; local
  processing unaffected. Trace step `pii_scrub` with counts by type.

---

## Rollout & validation

Same loop contract per train: failing tests first, implementation, default
suite green in CI (4 required checks), one PR per train closing its issues,
auto-merge, live E2E cycle, tracker update. Success metrics are test-pinned
per feature; Train 1's shadow sampling is additionally validated live by
forcing a sample rate of 1.0 against live Ollama and observing shadow rows.
