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
daari keys create --name ci --expires 30d
daari keys list
daari keys revoke <key_id>
```

Hashed storage; plaintext shown once. Supports daily/monthly budgets, RPM, TPM, tier caps, and an optional expiry (`--expires 30d|12h|45m` or an ISO-8601 timestamp). Existing keys with no expiry never expire. An expired key is a 401 `key_expired` (distinct from invalid/revoked) and writes an `auth.key_expired` audit row. `daari keys list` shows `expires` and a `status` of `active` / `expired` / `revoked`.

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
        key_ttl: 8h
    default_policy:
      tier_cap: L3
    deny_unmapped: false
```

Mint and revoke events land in the audit log with the claim that caused them.

## Secret references (`secret://`)

Any secret-bearing config value (frontier provider keys, org tokens,
Redis/Postgres URLs, OIDC client secrets) can be a `secret://` URI instead of
plaintext (issue #288). Resolution happens once at daemon startup by shelling
out — no vault SDK, no new dependency:

```yaml
frontier:
  providers:
    - id: openai
      keys:
        - secret://keychain/daari-frontier/naveen      # macOS security / Linux secret-tool
enterprise:
  shared_cache_token: secret://env-file//etc/daari/secrets.env#ORG_TOKEN
cache:
  redis_url: secret://exec/op read op://infra/daari-redis/url
```

- `secret://env-file/<path>#<KEY>` — `KEY=VALUE` line in a root-only file
  (quotes and `export ` prefixes are stripped).
- `secret://exec/<command>` — stdout of any operator command: `op read`,
  `vault kv get -field=...`, `aws secretsmanager get-secret-value ...`.
- `secret://keychain/<service>/<account>` — macOS Keychain via
  `security find-generic-password`, Linux secret-service via `secret-tool`.
- `secret://oauth/<token-url>?client_id=<id>&client_secret=<secret-ref>[&scope=…]`
  — no static upstream key at all; see below.

A ref that fails to resolve is fatal at startup with a message naming the ref
(never the value); `daari doctor` verifies every configured ref resolves.
Resolved values are redacted from gateway logs. Plain string values keep
working unchanged.

### OAuth client credentials (`secret://oauth`)

Enterprises that front OpenAI/Anthropic with an internal token service (workload
identity federation, OAuth client-credentials upstream auth) never want a
long-lived provider key on a laptop. The `oauth` scheme performs an RFC 6749
client-credentials grant against your token endpoint and uses the returned
`access_token` as the credential (#321):

```yaml
frontier:
  providers:
    - id: openai
      base_url: https://llm-proxy.corp.example.com/v1
      keys:
        - secret://oauth/https://idp.corp.example.com/oauth2/token?client_id=daari-laptops&client_secret=secret://keychain/daari-idp/client-secret&scope=llm.invoke&audience=https://llm-proxy.corp.example.com
```

- `client_id` (required) and `client_secret` (required) — the secret **must** be
  another `secret://` ref (`env-file`, `exec` or `keychain`); a plaintext secret
  in the URL is rejected. Percent-encode a nested ref that contains `&`, `+` or
  spaces.
- `scope`, `audience`, `resource` — optional, passed through verbatim for token
  services that require them.
- `auth=basic|post` — how the client authenticates to the token endpoint. Default
  `basic` (HTTP Basic, which RFC 6749 requires every server to support);
  `post` sends `client_id`/`client_secret` in the form body for IdPs configured
  for `client_secret_post`.
- `refresh_margin=<seconds>` — re-mint this long before `expires_in` (default 60).
  A response without `expires_in` is treated as a one-hour token.

The token is minted on the machine that uses it and cached in memory until
expiry minus the margin. Refresh is lazy: the next place that reads the
credential — frontier key rotation before each L6 attempt, org cache/learning
clients before each call — picks up a fresh token, with concurrent readers
sharing one token request. A refresh that fails (non-2xx, malformed body,
network error) raises with the endpoint in the message — never the secret or
token — and the L6 attempt fails over to the next provider rather than sending
an expired credential.

## Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:11435/v1/daari/stats
# expect 401 when key required
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:11435/v1/daari/stats
```

`daari doctor` includes a `secret_refs` row when any `secret://` value is
configured.

## Next

→ [Virtual keys feature](../features/virtual-keys.md) · [Security](../../resources/security.md)
