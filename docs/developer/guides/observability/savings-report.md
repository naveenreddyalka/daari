# Savings report

**Outcome:** See frontier spend avoided, priced per model.

## Steps

```bash
daari report
daari report --days 30
# Markdown export available via CLI flags / web UI export
curl -s 'http://127.0.0.1:11435/v1/daari/report?days=7' | python -m json.tool
```

Includes cache-trust panels when shadow samples exist.

## Where the numbers come from

Token counts are whatever the provider reported — `prompt_eval_count` /
`eval_count` from Ollama, the `usage` block from OpenAI-compatible and Anthropic
endpoints — recorded per model in the usage ledger alongside each request.

When a provider reports nothing (an interrupted stream, a backend that omits
`usage`), daari falls back to a characters-per-4 estimate and marks it. Any
response carrying an estimate sets `usage_estimated: true` in `daari_meta`, so a
client can always tell a measured count from a guessed one rather than having to
trust the number blindly.

Cost is then applied per model and per direction from `pricing.models`, since an
output token typically costs several times an input token and rates differ by an
order of magnitude across models. Models missing from that table are priced at the
flat `usage.frontier_price_per_1k_tokens` fallback — run `daari doctor` to list
them.

## Verify

After cached traffic, `estimated_saved_usd` > 0 in totals. To confirm counts are
measured rather than estimated, send a request with the `X-Daari-Meta: 1` header
and check that `usage_estimated` is `false`.

## Next

→ [Caching and trust](../../concepts/caching-and-trust.md) · [Budgets and frontier](../configuration/budgets-frontier.md)
