# Savings report

**Outcome:** See estimated frontier spend avoided.

## Steps

```bash
daari report
daari report --days 30
# Markdown export available via CLI flags / web UI export
curl -s 'http://127.0.0.1:11435/v1/daari/report?days=7' | python -m json.tool
```

Includes cache-trust panels when shadow samples exist.

## Verify

After cached traffic, `estimated_saved_usd` > 0 in totals.

## Next

→ [Caching and trust](../../concepts/caching-and-trust.md)
