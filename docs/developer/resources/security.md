# Security

Summary of [SECURITY.md](https://github.com/naveenreddyalka/daari/blob/main/SECURITY.md) and [ADR-0006](../../adr/0006-local-daemon-security.md).

## Trust boundaries

1. Localhost gateway — unauthenticated by default; tunnels must enable API keys
2. Lt tool execution — PolicyEngine allow/deny/ask
3. Org cache/learning — bearer tokens; cross-org leakage is in scope
4. Frontier escalation — only on L6; optional PII scrub

## Keys at rest

Config secrets accept [`secret://` references](../guides/configuration/auth-and-keys.md#secret-references-secret)
(env-file, exec command, OS keychain) resolved once at startup, so API keys
and tokens need not live as plaintext in `config.yaml` or env vars. Failed
refs are fatal, and resolved values are redacted from gateway logs.

## Report vulnerabilities

Use [GitHub Security Advisories](https://github.com/naveenreddyalka/daari/security/advisories/new) — do not open public issues.
