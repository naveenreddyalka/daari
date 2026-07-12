# daari — Local Learning PRD (Phase D)

> **Status:** Active — D1 feature train
> **Last updated:** 2026-07-11
> **Companion to:** [PRD v0.4](PRD.md), [ROADMAP Phase D](ROADMAP.md#phase-d--local-learning--collective-improvement-future), [intelligence PRD](intelligence.md)
> **Tracking:** GitHub issues labeled `auto-dev`; progress in [TRACKING.md](../TRACKING.md)

## Problem

daari now profiles prompts, traces decisions, and reports savings — but it never
learns from outcomes:

1. **Outcomes are discarded.** Whether a local answer was good enough (served
   without escalation) or weak (escalated to L6, warned
   `below_confidence_threshold`) is logged per-request and forgotten. Explicit
   user judgment (this answer was right/wrong) has no capture path at all.
2. **One global confidence threshold.** `routing.confidence_threshold` (0.7)
   applies identically to `git` one-liners and complex `code_gen`. Categories
   where L3 is reliably good still escalate; categories where L3 is reliably
   weak waste a local generation before escalating.
3. **Tier choice never improves.** `routing.category_policies` is static and
   hand-written. Nobody looks at accumulated evidence ("L3 serves 96% of
   `doc_qa` without escalation but only 40% of `code_gen`") to update it.

Privacy posture is unchanged: everything in this phase stays on-device under
`~/.daari/`. No prompts or completions are stored — outcome metadata only.

## Goals (D1 — personal feedback loop)

- Every routed model response records an **outcome row**: category, tier,
  confidence, escalated?, cache_hit?, latency — implicit, automatic, local.
- Users (or client UIs) can attach **explicit feedback** (`accept` / `reject`)
  to a response by `trace_id` via API and CLI.
- `daari learn stats` shows per-category × tier outcome evidence; `daari learn
  recommend` emits a ready-to-paste `routing.category_policies` YAML block
  derived from that evidence.
- An optional **routing tuner** derives per-category confidence thresholds
  from outcomes (bounded, off by default) so reliably-good categories stop
  escalating and reliably-weak ones escalate sooner.

## Non-goals

- No fine-tuning (D2) or anonymized stat export (D3/D4) in this train.
- No automatic rewriting of `config.yaml` — recommendations are printed, and
  runtime tuning is in-memory + evidence-gated, never persisted config edits.
- No new UI; the web dashboard can consume the new endpoint later.

## Feature D1a — Outcome store + feedback capture

New module `daari/learning/feedback.py` (SQLite pattern from
`observability/usage.py`):

- `FeedbackStore` at `~/.daari/feedback/feedback.sqlite3`, settings block
  `learning.*` (`enabled` default true, `path`).
- **Implicit capture**: router records after each model-tier response (not
  cache hits): `{ts, trace_id, category, complexity, tier, confidence,
  escalated, latency_ms}`. Best-effort — never fails the request (usage-ledger
  contract).
- **Explicit capture**: `POST /v1/daari/feedback {trace_id, signal:
  accept|reject}` joins by trace_id; `daari feedback <trace_id> --accept/--reject`
  CLI. Unknown trace_id → 404.
- Retention: `learning.max_rows` (default 20000), pruned oldest-first on write.

## Feature D1b — Learn stats + tier recommendations

- `FeedbackStore.stats(days)` aggregates per (category, tier): outcomes,
  escalation rate, explicit accept/reject counts, avg confidence, avg latency.
- `daari learn stats [--days N]` renders the table; `GET /v1/daari/learn/stats`
  serves it (web-ui later).
- `daari learn recommend [--days N] [--min-samples M]` (default 20): for each
  category with enough evidence, recommend the cheapest tier whose escalation
  rate ≤ 15% and explicit reject rate ≤ 10%; emit as a `routing.category_policies`
  YAML block with the evidence in comments. Below min-samples → no
  recommendation (never guess).

## Feature D1c — Routing tuner (per-category confidence thresholds)

- Settings `learning.auto_tune` (default **false**), `learning.tuner_min_samples`
  (default 50), bounds `[0.5, 0.9]`.
- When enabled, the router consults tuned thresholds by category: high local
  success (low escalation + accepts) lowers the threshold one notch (-0.05);
  high reject/escalation raises it (+0.05); always clamped to bounds, always
  requiring min samples.
- Tuned threshold recorded in the trace (`tuner` step: category, base,
  tuned) so every deviation from the global default is auditable.
- Never applies to explicit `X-Daari-Tier-Override` requests or agent flows.

## Rollout & validation

Same loop contract as previous trains: failing tests first, implementation,
default suite green in CI (4 required checks), auto-merge, live E2E cycle via
`scripts/autodev-local.sh`, tracker update. Explicit-feedback path validated
E2E by making a live request, posting feedback for its trace_id, and seeing it
in `daari learn stats`.

## Success metrics

- Implicit outcome rows appear for 100% of non-cache model responses (test-pinned).
- Explicit feedback by trace_id retrievable in stats (test-pinned, live-validated).
- `daari learn recommend` produces a valid `category_policies` YAML block that
  round-trips through `Settings.model_validate` (test-pinned).
- With auto_tune on and sufficient synthetic evidence, tuned thresholds change
  escalation behavior in the expected direction (test-pinned); off by default
  changes nothing (test-pinned).
