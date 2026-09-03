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

### Streams count once

A streamed request writes exactly one ledger row, whichever way the backend
surfaces usage: a single usage-only chunk before `[DONE]` (Ollama, vLLM), running
totals attached to every chunk, or nothing at all. daari keeps the *last* report
it sees rather than summing them, so cumulative providers cannot inflate the
count. The same figure feeds the client-visible usage — the final `usage` chunk on
`/v1/chat/completions`, `message_start.usage.input_tokens` and the cumulative
`message_delta.usage.output_tokens` on `/v1/messages`, and `prompt_eval_count` /
`eval_count` on the final `/api/chat` line — so what the client sees is what the
ledger, budgets and this report count. OpenAI-compatible local backends are asked
for counts with `stream_options.include_usage`. A client that disconnects
mid-stream never produces a second row.

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
