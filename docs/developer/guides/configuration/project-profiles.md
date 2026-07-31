# Project profiles (`.daari.yaml`)

**Outcome:** Commit per-repo routing defaults.

## Steps

```bash
daari project init /path/to/repo
daari project show /path/to/repo
```

```yaml
routing:
  max_tier_for_chat: L3
  no_frontier: true
  latency_budget_ms: 3000
client_id: my-repo
```

Clients send:

```
X-Daari-Project: /path/inside/repo
```

daari walks up to find `.daari.yaml`. Explicit headers always win over the profile.

## Verify

```bash
curl -s http://127.0.0.1:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Daari-Project: $PWD" \
  -H "X-Daari-Meta: true" \
  -d '{"model":"daari","messages":[{"role":"user","content":"hi"}]}'
```

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Profile ignored | Missing header; Cursor BYOK cannot set custom headers — use global config |
| Malformed YAML | Invalid keys are ignored; request still succeeds |

## Next

→ [Headers](../../reference/headers.md)
