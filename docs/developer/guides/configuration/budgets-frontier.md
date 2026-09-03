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
daari keys team-create eng --daily-budget 5
daari keys create ci-bot --daily-budget 2 --monthly-budget 20 --team eng --window 7d=10
```

Each window is checked independently. A key can carry several
`{duration, max_usd}` windows at once (`day`/`24h`, `month`/`30d`, `7d`, …);
team caps apply to every key on that team and the tighter of key vs team wins.
The org `frontier.*` caps above remain an outer ceiling. A key over budget gets
`402` naming the window that tripped and when it resets:

```json
{
  "error": {
    "type": "budget_exceeded",
    "message": "Virtual key daily frontier budget ($2.0000) exceeded — $2.4310 spent. Resets at 2026-08-28T00:00:00+00:00.",
    "client_id": "ci-bot",
    "window": "daily",
    "budget_usd": 2.0,
    "spend_usd": 2.431,
    "reset_at": "2026-08-28T00:00:00+00:00",
    "scope": "key"
  }
}
```

Clients do not have to wait for the `402`. Every successful response to a
budgeted key carries `x-daari-budget-remaining` / `-limit` / `-window` /
`-reset` / `-scope` for the window it will hit first (least USD left across
key and team), and the `402` repeats them with remaining `0` plus
`Retry-After`. See [Response headers](../../reference/headers.md#budget-headers).

### Operator alerts

A webhook fires when a request *pushes* a key or team window across a
threshold (default 80% and 100%). Empty URL disables. The POST is a
background task: a down hook is logged (`budget.alert_failed`) and never
delays or fails the chat response.

```yaml
alerts:
  budget_webhook_url: https://hooks.example/daari-budget   # Slack / ntfy / PagerDuty
  budget_thresholds: [0.8, 1.0]
```

Payload (never includes key material):

```json
{
  "scope": "key",
  "id": "a1b2c3d4",
  "name": "ci-bot",
  "window": "daily",
  "limit_usd": 5.0,
  "spent_usd": 4.12,
  "remaining_usd": 0.88,
  "threshold": 0.8,
  "reset_epoch": 1756944000
}
```

Each `(scope, id, window, threshold, reset_epoch)` fires at most once until
that window resets. Dedupe is in-memory on the process that handled the
request — two replicas can notify twice. Each fire writes a `budget.alert`
audit row and increments `daari_budget_alerts_total{scope,threshold}`.

Existing keys that only have `daily_budget_usd` / `monthly_budget_usd` are
migrated to `day` / `month` windows on first open; behavior is unchanged.

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

### OpenRouter slot (G3)

Use their catalog; do not clone it. The documented slot:

```yaml
frontier:
  enabled: true
  providers:
    - id: openrouter
      base_url: https://openrouter.ai/api/v1
      model: openrouter/auto   # or anthropic/claude-sonnet-4.5, etc.
      api_key_env: OPENROUTER_API_KEY
      zdr: false               # set true if the key is ZDR-only
```

`OPENROUTER_API_KEY` (or `DAARI_FRONTIER_API_KEY`) is BYOK — never committed. Outbound calls send `HTTP-Referer` and `X-Title: daari` for app attribution. L6 `daari_meta` records `cost_usd` (upstream) and `daari_cost_usd: 0`.

Local model suffixes: `daari:floor` is the smallest capable local tier (L3); `daari:nitro` prefers a warm / low-latency local backend. These do not call OpenRouter.

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
