# Virtual keys

**Outcome:** Issue scoped keys with budgets, RPM, and TPM limits.

## Steps

```bash
daari keys team-create eng --daily-budget 5 --rpm 120 --tpm 80000 --rpd 5000
daari keys create ci --daily-budget 2 --rpm 60 --tpm 40000 --rpd 2000 --team eng --window 7d=10
daari keys create shared-agent --user-daily-cap 2
daari keys list
daari report --by-team
daari usage --by-user
```

`--rpd` is requests per UTC day on the key or team. `0`, or omitting the flag, means unlimited.

Enable in config:

```yaml
server:
  virtual_keys:
    enabled: true
```

Use the plaintext secret once as `Authorization: Bearer …`.

## Model allowlists

Restrict a key or a team to specific models. Patterns are exact names or globs
(`claude-*`). Named groups are defined once in settings and referenced by
keys and teams. A key allowlist **intersects** the team allowlist: the key can
only narrow what the team already allows. Leave the field unset for today's
unrestricted behavior.

```yaml
model_groups:
  anthropic:
    - claude-*
  local:
    - llama3.2:3b
```

```bash
daari keys team-create eng --model-group anthropic --allowed-model 'llama*'
daari keys create ci --team eng --allowed-model llama3.2:3b
daari keys update <key_id> --allowed-model 'claude-*'
daari keys team-update <team_id> --model-group local
```

A request whose model is outside the allowlist is HTTP 403
`model_not_allowed` (the body names the model, never the key) and writes an
`auth.model_denied` audit row. Router fallback will not send that key to a
frontier model outside the allowlist.

## Verify

Call `/v1/chat/completions` with the key; exceed budget and confirm rejection.

## Next

→ [Auth and keys](../configuration/auth-and-keys.md)
