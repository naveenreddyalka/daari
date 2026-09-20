# Master key rotation

**Outcome:** Rotate `server.api_key` without a hard cutover.

The master key accepts a string (one key, unchanged) or a list. Every listed secret is accepted. Comparison is constant-time and checks the whole list. Virtual-key grace windows are separate; this is only the gateway master key.

## Steps

1. Add the new key beside the current one and restart (or roll the fleet). Both work immediately.

```yaml
server:
  api_key:
    - secret://env-file//etc/daari/master.env#CURRENT
    - secret://env-file//etc/daari/master.env#NEXT
```

`secret://` refs resolve per list entry, the same as a single string.

2. Roll admin clients, CI, and Helm `serviceMonitor.bearerTokenSecret` onto the new key.
3. Remove the old entry and restart. `daari doctor` warns on `master_keys` when more than two keys are still configured — overlap should be temporary.

Startup writes an `auth.master_key_overlap` audit row with `{"count": N}` when two or more keys are set. The row never contains key material.

## Verify

A request with either key succeeds; a request with neither is 401. `daari audit list --action auth.master_key_overlap` shows the count only.

## Next

→ [Doctor and health](doctor-health.md) · [Upgrade](upgrade.md)
