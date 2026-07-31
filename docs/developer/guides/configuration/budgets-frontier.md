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

Soft warnings then hard stop. Per-virtual-key budgets also apply.

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
