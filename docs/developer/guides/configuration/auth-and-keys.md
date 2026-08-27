# Auth and virtual keys

**Outcome:** Lock down the gateway and issue per-client keys.

## Master API key

```yaml
server:
  api_key: "replace-me"
```

Clients send `Authorization: Bearer <key>` or `x-api-key`. `/health` stays open.

Tunnel setup (`daari setup cursor --tunnel`) auto-generates a key when unset.

## Virtual keys

```bash
daari keys create --name alice --daily-budget 5
daari keys list
daari keys revoke <key_id>
```

Hashed storage; plaintext shown once. Supports daily/monthly budgets, RPM, TPM, tier caps.

```bash
daari keys create --name ci --rpm 60 --tpm 40000
```

## Rate limits

Defaults apply to every key (including the master key). A virtual key's `--rpm` / `--tpm` override the global defaults for that key. `0` means unlimited.

```yaml
rate_limit:
  rpm: 60
  tpm: 40000
  model_rpm: 0          # 0 = same as rpm, scoped per model
  model_tpm: 0
  max_in_flight: 8      # 0 = no concurrency gate
  queue_size: 32        # waiters before 503 + Retry-After
  retry_after_seconds: 1
```

Counters live in Redis when `cache.backend: redis` (`daari:rl:` prefix); otherwise SQLite next to the virtual-key store. Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. `/metrics` exposes the configured limits and current in-flight / queued gauges.

## SSO (admin)

OIDC/JWKS for admin surfaces — see ADR and enterprise settings (`enterprise.sso`).
RSA (`RS256`/`384`/`512`) and EC (`ES256`/`384`/`512`) signing keys; `use: "sig"`
is preferred when a JWKS also lists encryption keys. HMAC stub remains for
local/dev when JWKS unset.

### IdP-minted virtual keys (MDM)

Alongside `daari enterprise bootstrap`, map an IdP claim to key policy so
devices never need a hand-distributed `dk_…` secret. First verified
`POST /v1/daari/sso/session` mints a key; later logins resync limits.
When the mapped claim disappears, the key is revoked. Unmapped claims use
`default_policy` or `403` if `deny_unmapped: true`.

```yaml
enterprise:
  sso:
    enabled: true
    jwks_url: https://idp.corp/jwks
    mint_virtual_key_on_login: true
    mapping_claim: groups
    key_mappings:
      eng:
        daily_budget_usd: 5
        rpm: 120
        tier_cap: L4
        boundary_profile: fintech
      contractors:
        tier_cap: L3
    default_policy:
      tier_cap: L3
    deny_unmapped: false
```

Mint and revoke events land in the audit log with the claim that caused them.

## Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:11435/v1/daari/stats
# expect 401 when key required
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:11435/v1/daari/stats
```

## Next

→ [Virtual keys feature](../features/virtual-keys.md) · [Security](../../resources/security.md)
