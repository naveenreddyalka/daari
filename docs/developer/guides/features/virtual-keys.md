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

## Cache scope

The org-shared cache is the default: identical prompts (L0) and similar prompts
(L1) are reused across every key. That is the hit-rate win. A team handling
confidential material can opt into a boundary instead.

`cache_scope` is `global` (default), `team`, or `key`, on both a virtual key
and a team. The stricter setting wins (`key` over `team` over `global`), so a
team set to `team` isolates every member key even when the key itself stays
`global`. `team` folds `team_id` into the L0 exact key, the Redis L0 key, and
the L1 context key. `key` folds `key_id` the same way. `global` leaves those
hashes unchanged, so entries written before the flag stay reachable.

Two keys on the same team with `cache_scope: team` share entries. A key on
another team does not, including an L1 hit on a merely similar prompt.
Requests with no auth (master key off, no virtual keys) stay `global`.
`X-Daari-No-Cache` still skips the cache entirely.

```bash
daari keys team-create legal --cache-scope team
daari keys create counsel --team legal
daari keys create solo --cache-scope key
daari keys list
```

`daari keys list` prints the effective scope. `POST /introspect` includes
`cache_scope` for the token (never the secret).

## Verify

Call `/v1/chat/completions` with the key; exceed budget and confirm rejection.

## Next

→ [Auth and keys](../configuration/auth-and-keys.md)
