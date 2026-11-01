# Security

Summary of [SECURITY.md](https://github.com/naveenreddyalka/daari/blob/main/SECURITY.md) and [ADR-0006](../../adr/0006-local-daemon-security.md).

## Trust boundaries

1. Localhost gateway — unauthenticated by default; tunnels must enable API keys
2. Lt tool execution — PolicyEngine allow/deny/ask
3. Org cache/learning — bearer tokens; cross-org leakage is in scope
4. Frontier escalation — only on L6; optional PII scrub

## Keys at rest

Config secrets accept [`secret://` references](../guides/configuration/auth-and-keys.md#secret-references-secret)
(env-file, exec command, OS keychain) resolved at startup and refreshed on a
TTL / env-file mtime by default (#1204), so API keys
and tokens need not live as plaintext in `config.yaml` or env vars. Failed
refs are fatal, and resolved values are redacted from gateway logs.

Persisted prompt/response payloads (response store, request log, L0/L1 disk
cache) can also be AES-GCM encrypted with a customer-held
`security.at_rest_key` — see [at-rest encryption](at-rest-encryption.md)
(#1958).

## Offline / air-gapped egress

Set `security.offline_mode: true` to fail-closed on off-box egress from shared
httpx clients (frontier, MCP, TTS, webhooks, enforcement sync, OTel). Loopback
and RFC1918 hosts keep working; on-estate DNS names go in
`security.offline_allow_hosts`. `daari validate` warns on each configured
off-box surface; `daari doctor` reports mode state; refused attempts emit
`security.offline_egress_refused` via the request log (#2034).

## Report vulnerabilities

Use [GitHub Security Advisories](https://github.com/naveenreddyalka/daari/security/advisories/new) — do not open public issues.
