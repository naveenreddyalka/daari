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

## Per-key budgets

A virtual key can carry its own caps, charged only against that key's own spend:

```bash
daari keys create ci-bot --daily-budget 2 --monthly-budget 20
```

Each window is checked independently, and the caps above act as an outer ceiling
that no key can exceed regardless of its own allowance. A key over budget gets
`402` naming the window that tripped, so a client can tell "I am out of budget"
from "the org is out of budget":

```json
{
  "error": {
    "type": "budget_exceeded",
    "message": "Virtual key daily frontier budget ($2.0000) exceeded — $2.4310 spent.",
    "client_id": "ci-bot",
    "window": "daily",
    "budget_usd": 2.0,
    "spend_usd": 2.431
  }
}
```

Only frontier (L6) usage counts. Local tiers and cache hits are free and never
consume a budget. Spend is priced per model from `pricing.models`, so a key's
remaining allowance reflects the models it actually used.

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

Configure `frontier.providers` (ordered list) for OpenAI-compatible bases, Anthropic, OpenRouter, etc. Circuit breakers and key rotation ship with the L6 pool. A provider whose `provider` is `anthropic`/`claude`, or whose `base_url` contains `anthropic.com`, is sent native Messages API payloads (`POST …/messages`, `x-api-key`) rather than an OpenAI `/chat/completions` body.

Clients may send OpenRouter's `provider` object (`zdr`, `sort`, `order`, `max_price`, …). daari stores it on the request, passes it through when the L6 slot is OpenRouter, and **fails closed** (HTTP 400) if `zdr: true` and no configured slot declares `zdr: true`. Chosen provider, `usage.cost`, and cached tokens land in `daari_meta`.

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
