# daari — Local Learning PRD (Phase D)

> **Status:** Active — D1 shipped (#53–#55); D2 feature train in progress
> **Last updated:** 2026-07-12
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

---

# Phase D2 — local fine-tuning from accumulated feedback

## Problem (D2)

D1 captures *whether* answers were good, but the models themselves never
improve. Two facts make fine-tuning attractive here:

1. **Accepted answers are free training data.** Every explicit accept — and
   especially every L6 frontier answer the user accepted — is a
   demonstration of the output the local model *should* have produced.
   Frontier-accepted examples are distillation data: they teach the 3B model
   to answer like the frontier model for this user's actual workload.
2. **Apple Silicon can do this locally.** LoRA fine-tuning of a 3B model via
   `mlx-lm` runs on an M-series MacBook in minutes for small datasets. No
   cloud, no data leaves the device — consistent with daari's privacy posture.

D1 deliberately stored no prompt/completion text, so D2 adds a separate,
**opt-in** capture path with its own store and clear controls.

## Goals (D2)

- Opt-in capture of (prompt messages, completion) training examples at serve
  time, promoted to `accepted` when explicit feedback arrives.
- One-command export to an `mlx-lm`-compatible chat dataset with a
  deterministic train/valid split.
- One-command LoRA fine-tune wrapper (`daari learn finetune`) that builds and
  runs the `mlx_lm` job — with `--dry-run` for inspection and a clean error
  when `mlx-lm` isn't installed. CI never trains; it pins command
  construction and gating only.

## Non-goals (D2)

- No automatic serving of adapters through Ollama (MLX adapters aren't
  directly loadable by Ollama; fuse/convert to GGUF is documented as a manual
  follow-up, revisited in a later train).
- No scheduled/automatic retraining — fine-tuning is always user-invoked.
- No quality benchmarking harness yet (candidate for D2 follow-up).

## Feature D2a — Opt-in training example capture

- Settings: `learning.capture_examples` (default **false**),
  `learning.examples_path` (default `~/.daari/training/examples.sqlite3`),
  `learning.examples_max_rows` (default 5000, pruned oldest-first).
- New `daari/learning/examples.py`: `ExampleStore` rows `{ts, trace_id,
  category, complexity, tier, model, messages_json, completion, accepted}`.
- Router hook (non-stream and stream paths): when capture is enabled, store
  the example for model-tier responses (L3–L6; L6 = distillation data).
  Cache hits and agent/tool flows are never captured. Best-effort writes.
- Explicit feedback join: an `accept` for a trace_id marks the stored example
  accepted; a `reject` deletes it.
- CLI: `daari learn examples [--limit N]` (summary list, no full text dump),
  `daari learn examples --clear` (wipe the store).

## Feature D2b — Dataset export

- `daari learn export-dataset --out DIR [--only-accepted] [--split 0.9]
  [--min-examples 8]`: writes `train.jsonl` + `valid.jsonl` where each line is
  `{"messages": [...system/user/assistant turns..., {"role": "assistant",
  "content": completion}]}` — the chat format `mlx_lm lora --data` consumes.
- Deterministic split (hash of trace_id, not random) so re-exports are stable.
- Below `--min-examples`: exit non-zero with a clear message (never train on
  a handful of rows silently).

## Feature D2c — Fine-tune runner

- `daari learn finetune [--model M] [--iters N] [--only-accepted] [--dry-run]`
  (default model `mlx-community/Llama-3.2-3B-Instruct-4bit`, iters 100):
  exports the dataset to `~/.daari/training/runs/<ts>/data`, then builds
  `python -m mlx_lm lora --train --model M --data DATA --iters N
  --adapter-path ~/.daari/training/runs/<ts>/adapters`.
- `--dry-run` prints the exact command and dataset counts without running.
- Missing `mlx-lm`: exit non-zero with the pip install hint. Never a hard
  dependency of daari itself.
- Run metadata (`run.json`: model, iters, example counts, timestamps) written
  next to the adapters for auditability.

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
