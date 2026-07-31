# Product boundaries

**Outcome:** Refuse clearly out-of-scope prompts locally (zero model tokens).

## Prerequisites

Daemon running; decide product domain topics.

## Steps

Copy [`examples/boundaries/fintech-assist.yaml`](https://github.com/naveenreddyalka/daari/blob/main/examples/boundaries/fintech-assist.yaml) into `~/.daari/config.yaml`, or PATCH `/v1/daari/config`:

```yaml
boundaries:
  enabled: true
  mode: warn          # dry-run first
  product_name: "Credit Assist"
  allow_topics: ["credit score", "credit card"]
  deny_topics: ["python", "wedding"]
  refuse_message: "I only help with credit questions."
  clear_out_threshold: 0.75
  clear_in_threshold: 0.75
```

When confident, set `mode: block`.

## Verify

```bash
python scripts/smoke_boundaries.py
# or curl with X-Daari-Meta — expect tier=boundary on deny topics
```

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Too many refuses | Lower thresholds or use `mode: warn`; expand `allow_topics` / `examples_in` |
| Never refuses | Confirm `enabled: true` and restart / PATCH rebuilds engine |

## Next

→ [Concept](../../concepts/boundaries-and-guardrails.md) · [ADR-0015](../../../adr/0015-product-boundaries.md)
