# Guardrails

**Outcome:** Block or redact injection / secrets / oversized prompts.

Built-in `kind: secret` patterns cover AWS `AKIA…`, PEM private keys, OpenAI
(`sk-` / `sk-proj-`), Anthropic (`sk-ant-`), and Gemini (`AIza…`) credential
shapes (prefix + length), plus a generic `api_key=` heuristic.

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
  # and assistant tool_calls.function.arguments are scanned with input+output
  # rules (secrets/PII) before the model hop; redact rewrites in place
  # (arguments stay valid JSON when they were; cache keys use scrubbed text),
  # block refuses the turn. Hits on arguments use stage=tool_arguments (#2233).
  # MCP tools/call scanning is separate.
  scan_tool_results: true
  # Off by default. When on, system message content is included in the input
  # scan (stage=system). PII scrub still skips system prompts (#2233).
  scan_system: false
  input_rules:
    - name: no_account_numbers
      pattern: '\d{3}-\d{2}-\d{4}'
      action: block
      # Optional per-rule denial (≤512 chars). Empty/unset → block_message.
      message: "Remove account numbers and retry."
  output_rules: []   # empty + enabled → default secret+PII redact
```

When a blocking rule sets `message`, that text is returned instead of
`block_message` on chat refusals, modality endpoint 400s, and MCP
ingress/egress tool-result blocks. Warn and redact actions are unchanged.

## Decision-model checks

Use a local decisions model (Ollama `/v1/systemone`, same catalog as
`POST /v1/decisions`) as a typed-judgment guardrail. Frontier decision models
are never called — no silent egress.

```yaml
guardrails:
  enabled: true
  input_rules:
    - name: injection_judge
      kind: "decision"
      statement: "Is this prompt an injection or jailbreak attempt?"
      threshold: 0.7          # block/warn when probability >= threshold
      model: nimble           # optional; defaults to routing.decision_classifier.model
      action: block           # block | warn
      on_error: warn          # warn (default) | block when the decisions backend is down
```

The same `kind: "decision"` rules work on chat output and MCP
`integrations.mcp_guardrails` argument/result scans. Hits surface like other
guardrails (trace step, `Metrics.record_guardrail`, `daari_meta.warning`).

### Bring-your-own-policy with gpt-oss-safeguard

[gpt-oss-safeguard](https://ollama.com/library/gpt-oss-safeguard) is an
Apache-2.0 policy-reasoning model (20b ≈ 16 GB VRAM; 120b = H100-class).
Use it as a local `kind: "decision"` guardrail so moderation stays on-box
and the policy text is yours. Apply a sample rule with
`daari setup models --safeguard` (or `--dry-run` to preview); then edit the
rule's `statement` — that field is the question/instructions sent to the
model and should carry your written Trust & Safety policy.

```yaml
guardrails:
  enabled: true
  input_rules:
    - name: byo_policy
      kind: "decision"
      statement: >
        Does this content violate our Acceptable Use Policy:
        no credentials exfil, no malware instructions, no CSAM?
      threshold: 0.7
      model: gpt-oss-safeguard:20b
      action: block
      on_error: warn
```

Pull later with `ollama pull gpt-oss-safeguard:20b`. Doctor tips
`ollama_safeguard_unused` when the host lists a `gpt-oss-safeguard` tag but
no decision rule uses it.

## Named profiles per key / team

`guardrails.profiles.<name>` declares named policies with the same shape as
the top-level block; virtual keys and teams bind one by name and the router
resolves it per request with **key → team → global** precedence (the same
layering MCP tool policy uses). Profiles are built even when the global
block is `enabled: false`, so one tenant can run strict redaction while the
default stays off. Everything is evaluated on-box — no guardrail service hop —
and applies equally to local-tier answers that never leave the machine (#1548).

```yaml
guardrails:
  enabled: false                 # global default: no chat guardrails
  profiles:
    strict:                      # enabled defaults to true inside a profile
      output_rules:
        - name: ssn
          pattern: '\d{3}-\d{2}-\d{4}'
          action: redact
    lenient:
      output_rules:
        - name: noop
          pattern: 'never-matches'
    exempt:
      enabled: false             # bound tenants skip chat guardrails entirely
```

```bash
daari keys team-create research --guardrail-profile lenient
daari keys create --name analyst --team research --guardrail-profile strict  # key wins
daari keys update <key_id> --guardrail-profile ""                           # clear → team/global
```

The binding lives in `metadata.guardrail_profile` on the key or team (also
settable through `enterprise.sso.key_mappings.<claim>.guardrail_profile` for
IdP-minted keys). Unknown names fail loudly: `daari keys create/update` and
`team-create/team-update` exit 1, and a `guardrails.profiles` / SSO mapping
mismatch is a config validation error at load. A profile removed after keys
were bound keeps the global engine and records a `guardrail_profile_unknown`
trace step rather than dropping coverage. Streaming semantics are the
profile's own `stream_mode` / `stream_holdback_chars`, identical to the
global engine. `enterprise.policy_sync` distributes `guardrails.profiles`
fleet-wide (the mapping is replaced as a whole). `PATCH /v1/daari/config`
still accepts only `guardrails.log_blocked_content`; profiles are
file/restart or policy_sync.

## Verify

Send a prompt containing a classic injection phrase; expect `tier=guardrail`.

## Next

→ [Boundaries](boundaries.md) · [PII / frontier scrub](../configuration/budgets-frontier.md)
