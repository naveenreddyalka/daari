# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.2.x   | Yes |
| < 1.2   | No — upgrade |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately via [GitHub Security Advisories](https://github.com/naveenreddyalka/daari/security/advisories/new) ("Report a vulnerability"). You should get an acknowledgment within a few days. Please include reproduction steps and the affected version/config.

## Security model (what to look at)

daari is a **local-first** daemon; its trust boundaries are:

1. **Localhost gateway** (`127.0.0.1:11435`) — unauthenticated by default ([ADR-0006](docs/adr/0006-local-daemon-security.md)). Anything that lets a non-local caller reach it, or a local caller escalate beyond routing, is in scope.
2. **Tunnel exposure** — `daari setup cursor --tunnel` publishes the gateway via cloudflared and auto-enables API-key auth (`server.api_key`, Bearer or `x-api-key`). Auth bypasses on non-health endpoints are high severity.
3. **Lt tool execution** — shell commands are gated by the [execution policy](docs/adr/0012-execution-policy.md) (allow/deny/ask, default deny unknown). Policy bypasses or injection into allowed commands are high severity.
4. **Org shared cache/learning service** — optional bearer-token service; cross-org data leakage or token bypass is in scope.
5. **Frontier escalation** — prompts can leave the machine only on L6 escalation (budget-gated, optional PII scrub). Anything causing unexpected data egress is in scope.

Secrets: daari never stores frontier API keys in its config; they come from environment variables. Reports about key handling in setup recipes are welcome.
