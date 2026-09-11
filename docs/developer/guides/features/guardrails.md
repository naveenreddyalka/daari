# Guardrails

**Outcome:** Block or redact injection / secrets / oversized prompts.

## Steps

```yaml
guardrails:
  enabled: true
  max_prompt_chars: 100000
  injection_action: block
  block_message: "Request blocked by daari guardrail."
  # buffered (default) = scan the full answer before the first SSE byte.
  # incremental = holdback window so secrets spanning chunks never leak; also
  # keeps L6 frontier relay eligible (#375).
  stream_mode: incremental
  stream_holdback_chars: 256
  # Off by default. When on, OpenAI role=tool / Anthropic tool_result contents
  # are scanned with output rules (secrets/PII) before the model hop; redact
  # rewrites in place (cache keys use scrubbed text), block refuses the turn.
  # System/user/assistant are unchanged. MCP tools/call scanning is separate.
  scan_tool_results: true
  input_rules: []
  output_rules: []   # empty + enabled → default secret+PII redact
```

## Verify

Send a prompt containing a classic injection phrase; expect `tier=guardrail`.

## Next

→ [Boundaries](boundaries.md) · [PII / frontier scrub](../configuration/budgets-frontier.md)
