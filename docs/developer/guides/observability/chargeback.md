# Chargeback export

**Outcome:** Hand finance a per-request CSV of what each key and team spent, and what local routing avoided.

The day-aggregated usage ledger (`daari report`) is the summary. Chargeback needs one row per completed request. That log is **off by default** so an upgrade does not add write volume. Turn it on when a platform team needs an auditable $0-local vs frontier split.

## Steps

```yaml
usage:
  spend:
    enabled: true
    path: ~/.daari/usage/spend.sqlite3   # ignored when observability.backend is postgres
observability:
  backend: sqlite   # or postgres + postgres_url, same switch as the usage ledger
  retention:
    spend_days: 90  # 0 keeps rows forever
```

```bash
daari spend export --since 2026-01-01T00:00:00Z --format csv
daari spend export --since 30d --format jsonl --team platform
daari spend export --since 7d --format csv --key key_abc123
```

`--since` accepts an ISO-8601 timestamp or a relative window (`7d`, `12h`). `--key` and `--team` are exact filters. CSV and JSONL both stream one row at a time.

Each row has: timestamp, request id, key id, team id, client id, model, tier, input / output / cached tokens, `cost_usd` (what this request cost; $0 on local tiers), `cost_avoided_usd` (the frontier price those tokens would have paid), and a cache-hit flag.

`cost_avoided_usd` uses `pricing.models` for the model the client asked for. Models missing from that table use `usage.frontier_price_per_1k_tokens`. Frontier (`L6`) rows keep the real cost and record $0 avoided.

`daari prune` applies `observability.retention.spend_days` the same way it prunes traces and the day ledger. Postgres replicas share the table when `observability.backend` is `postgres`.

## Verify

With the log enabled, complete a local request and export with a fixed `--since` that covers it. The row's `cost_usd` is 0 and `cost_avoided_usd` is greater than 0. With `usage.spend.enabled: false`, no spend database is created.

## Next

→ [Savings report](savings-report.md) · [Budgets and frontier](../configuration/budgets-frontier.md)
