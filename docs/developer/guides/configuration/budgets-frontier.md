# Budgets and frontier (L6)

**Outcome:** Cap spend and configure ordered L6 providers.

## Budgets

```yaml
frontier:
  enabled: true
  daily_budget_usd: 5
  monthly_budget_usd: 50
  soft_budget_ratio: 0.8
```

Soft warnings then hard stop.

!!! warning "Per-key budgets are not yet isolated"
    A virtual key can carry its own budget, but spend is currently checked against
    total frontier spend rather than that key's own usage, so one key's traffic can
    exhaust another key's allowance. Track
    [#158](https://github.com/naveenreddyalka/daari/issues/158). Until it lands,
    treat `frontier.daily_budget_usd` as the only reliable cap.

## Pricing

Spend is computed per model and per direction from `pricing.models`, in USD per
1M tokens:

```yaml
pricing:
  models:
    gpt-4o:
      input_per_1m: 2.50
      output_per_1m: 10.00
      cached_input_per_1m: 1.25
    my-self-hosted-model:
      input_per_1m: 0.0
      output_per_1m: 0.0
```

Names match on longest prefix, so a `gpt-4o` entry also prices
`gpt-4o-2024-08-06`. Anything unmatched falls back to the flat
`usage.frontier_price_per_1k_tokens`, which ignores direction and will misprice a
model whose output rate differs sharply from its input rate. `daari doctor` warns
about models being billed at that fallback, so add an entry when you adopt a new
model or your budgets will drift from your real invoice.

## Providers / fallback

Configure `frontier.providers` (ordered list) for OpenAI-compatible bases, Anthropic, OpenRouter, etc. Circuit breakers and key rotation ship with the L6 pool.

API keys via environment (never commit):

```bash
export DAARI_FRONTIER_API_KEY=sk-...
# or provider-specific envs documented in config reference
```

## PII / slim

```yaml
frontier:
  scrub_pii: true
  slim_prompts: true
```

## Verify

Force L6 only in a test env with a tiny budget; confirm soft warning then block in traces/`daari_meta`.

## Next

→ [Config reference](../../reference/config.md)
