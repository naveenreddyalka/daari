# Guardrails

**Outcome:** Block or redact injection / secrets / oversized prompts.

## Steps

```yaml
guardrails:
  enabled: true
  max_prompt_chars: 100000
  injection_action: block
  block_message: "Request blocked by daari guardrail."
  input_rules: []
  output_rules: []   # empty + enabled → default secret+PII redact
```

## Verify

Send a prompt containing a classic injection phrase; expect `tier=guardrail`.

## Next

→ [Boundaries](boundaries.md) · [PII / frontier scrub](../configuration/budgets-frontier.md)
