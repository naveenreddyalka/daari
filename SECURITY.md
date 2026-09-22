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

## Request body size

`server.max_body_bytes` (default 10 MiB, env `DAARI_SERVER__MAX_BODY_BYTES`) caps
inbound bodies **before** middleware buffers them. Oversized requests return
**413** (OpenAI `error.code=request_too_large`; Anthropic `type=error` /
`invalid_request_error`). File and audio upload routes use a higher floor so
`files.max_total_bytes` can still govern stored uploads. Set `0` to disable.
`daari_rejects_total{kind="body_too_large"}` counts denials.

## TLS for the gateway

Two supported modes (pick one; do not double-terminate without understanding the hop):

### 1. Native TLS / mTLS (`daari serve`)

Set `server.tls.cert_file` + `server.tls.key_file` (env: `DAARI_SERVER__TLS__CERT_FILE` /
`DAARI_SERVER__TLS__KEY_FILE`, or flags `--tls-cert` / `--tls-key`). Uvicorn then
serves HTTPS. The key path may be a `secret://` ref that resolves to PEM material.
Optional `server.tls.client_ca` (or `--tls-client-ca`) enables mutual TLS
(`ssl_cert_reqs=CERT_REQUIRED`) so clients without a valid cert are rejected.

Helm: `tls.enabled=true` with `tls.existingSecret` mounts the Secret at
`/etc/daari/tls` and wires the env vars; probes use `scheme: HTTPS`.

`daari doctor` warns when `server.api_key` is set, TLS is off, and `server.host`
is non-loopback (plaintext keys on the wire).

### 2. TLS terminated by reverse proxy / ingress

Keep daari on HTTP behind nginx, Caddy, Traefik, cloudflared, or a Kubernetes
Ingress/Gateway that terminates TLS. Trust only the proxy's hop:

- Do not expose the daari port on a non-loopback interface without auth + TLS
  (native or proxy).
- If the proxy forwards client identity, treat `X-Forwarded-For` /
  `X-Forwarded-Proto` as advisory unless you control the proxy and strip
  spoofed headers at the edge.
- Health checks (`/health`, `/ready`) stay reachable for the proxy; protect
  `/v1/*` with `server.api_key` or virtual keys as usual.
