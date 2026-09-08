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

### Window rollover (opt-in)

By default unused headroom disappears at reset. Set `rollover: true` on a
window so leftover USD carries into the next period's **effective** limit:

```json
{ "duration": "month", "max_usd": 100, "rollover": true, "rollover_cap_multiple": 2.0 }
```

CLI: `daari keys create bot --window month=100:rollover`.

At each period boundary, unused headroom (`prev_effective − spent`, floor 0)
becomes carry. Effective limit is `min(base + carry, base × rollover_cap_multiple)`
(default cap **2×** the base) so idle keys cannot accumulate forever. Carry is
persisted on the usage ledger (`budget_window_state`) so SQLite and Postgres
replicas agree. Headers, `402` bodies, and budget alert webhooks all report the
**effective** limit and remaining.

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
that window resets. With `cache.backend: redis` (the same Redis as L0/L1 and
rate limits), the fleet claims that tuple with `SET NX EX` before delivery;
the TTL runs until the window reset so keys expire on their own. Without
Redis, dedupe stays in-memory on the process that handled the request — two
replicas can notify twice. A Redis error still delivers the alert and logs
`budget.alert_dedupe_degraded` (never drop a page because the claim store
is down). Each fire writes a `budget.alert` audit row and increments
`daari_budget_alerts_total{scope,threshold}`.

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
`gpt-4o-2024-08-06`. A vendor prefix resolves the same way:
`anthropic.claude-fable-5-1` and `models/gemini-3.8-flash` use the shipped
id. Anything unmatched falls back to the flat
`usage.frontier_price_per_1k_tokens`, which ignores direction and will misprice a
model whose output rate differs sharply from its input rate. `daari doctor` warns
about models being billed at that fallback, so add an entry when you adopt a new
model or your budgets will drift from your real invoice.

### Shipped list prices (captured 2026-09-07)

The default table still includes the 2024 entries (`gpt-4o`, `gpt-4o-mini`,
`claude-3-5-sonnet`, `claude-3-5-haiku`, `claude-3-opus`) at their previous
rates. Current flagship and workhorse models, USD per 1M tokens:

| Model | Input | Cached input | Output | Source |
|-------|------:|-------------:|-------:|--------|
| `claude-fable-5-1` | 10.00 | 0.25 | 50.00 | [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview) |
| `claude-opus-5` | 5.00 | 0.50 | 25.00 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| `claude-sonnet-5` | 2.00 | 0.20 | 10.00 | Anthropic pricing |
| `claude-haiku-4-5` | 1.00 | 0.10 | 5.00 | Anthropic pricing |
| `gpt-6-astra` | 10.00 | 1.00 | 50.00 | OpenAI standard short-context tier |
| `gpt-5.6` / `gpt-5.6-sol` | 4.00 | 0.40 | 20.00 | OpenAI promo through 2026-11-21 ([Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)) |
| `gpt-5.6-terra` | 2.00 | 0.20 | 12.00 | OpenAI API pricing |
| `gpt-5.6-luna` | 0.20 | 0.02 | 1.20 | OpenAI API pricing |
| `gemini-3.8-flash` | 0.75 | 0.075 | 3.75 | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) intro rate through 2026-12-31 |

`gpt-5.6` is the Sol alias. Longer keys win, so `gpt-5.6-luna` is not priced
as Sol. Gemini 3.8 Flash's published standard rate becomes $1.50 / $7.50 on
2027-01-01; the shipped default is the intro rate in effect now. Override
`pricing.models` when that date passes or when a provider changes a quote.

### Known limitation: GPT-6 Astra long-context surcharge

Threshold pricing is out of scope. `gpt-6-astra` is billed at the short-context
list rate ($10 input / $1 cached / $50 output per 1M) regardless of prompt
length.

OpenAI reprices the **entire** request once input exceeds 272K tokens: 2× input
and cached-input, 1.5× output ($20 / $2 / $75). Operators budgeting 1M-context
Astra traffic will see daari spend, budget remaining, and cost headers below
the invoice for those calls. Set a higher `pricing.models` override if that
traffic is the common case.

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
