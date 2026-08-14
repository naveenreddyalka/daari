# Virtual keys

**Outcome:** Issue scoped keys with budgets, RPM, and TPM limits.

## Steps

```bash
daari keys create --name ci --daily-budget 2 --rpm 60 --tpm 40000
daari keys list
```

Enable in config:

```yaml
server:
  virtual_keys:
    enabled: true
```

Use the plaintext secret once as `Authorization: Bearer …`.

## Verify

Call `/v1/chat/completions` with the key; exceed budget and confirm rejection.

## Next

→ [Auth and keys](../configuration/auth-and-keys.md)
