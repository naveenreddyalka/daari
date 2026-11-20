# Claude Managed Agents (self-hosted)

**Outcome:** Point self-hosted Claude Managed Agents (CMA) inference at daari's
Anthropic facade so L0–L5 absorb repeat agent turns locally before any frontier
Claude call.

This is a community setup path. daari is not an Anthropic product or partner —
it accepts the Claude Messages API shape that CMA already supports for custom
gateways.

## Prerequisites

- `daari serve` on `http://127.0.0.1:11435` (or a tunnel to that facade)
- Self-hosted CMA stack (`cma-server` + Postgres + workers) configured per
  [Anthropic's self-hosted data and access docs](https://platform.claude.com/docs/en/managed-agents/self-hosted-data-and-access)

## Steps

1. Start daari:

```bash
daari serve
```

2. In CMA, set the inference / Claude Messages base URL to daari (no trailing
   `/v1` if CMA appends `/v1/messages` itself):

```text
http://127.0.0.1:11435
```

Use a tunnel URL instead when CMA workers run off-box.

3. Auth: send daari's virtual key the same way you would for Claude Code —

| Header | Value |
|--------|-------|
| `x-api-key` | `daari-local` (or your virtual key) |
| or `Authorization` | `Bearer <virtual-key>` |

4. CMA sends `metadata.user_id: "cma-server"` on every model call. daari
   **must not** reject that value — it is accepted and used for end-user
   attribution / caps like any other `metadata.user_id`. Do not strip it on
   the Anthropic adapter.

## Managed Agents attribution headers

CMA may also send `anthropic-managed-agents-*` request headers. daari accepts
them (logged on `anthropic_messages_request` as `managed_agents_headers`,
otherwise ignored). They are never a validation failure.

## Verify

```bash
curl -s http://127.0.0.1:11435/v1/messages \
  -H 'content-type: application/json' \
  -H 'anthropic-version: 2023-06-01' \
  -H 'x-api-key: daari-local' \
  -H 'anthropic-managed-agents-session-id: verify' \
  -d '{
    "model": "daari",
    "max_tokens": 16,
    "messages": [{"role": "user", "content": "hi"}],
    "metadata": {"user_id": "cma-server"}
  }'
```

Expect HTTP 2xx (not 422). Then `daari report` / `daari doctor` — when the
facade is up, doctor tips that CMA can target this listener.

## Troubleshoot

| Problem | Fix |
|---------|-----|
| 422 on `metadata.user_id` | Upgrade daari; `cma-server` must be allowed |
| Still hits Anthropic cloud | Confirm CMA inference base URL points at daari |
| 401 / missing key | Set `x-api-key` or Bearer virtual key on CMA → daari |

→ [Claude Code](claude-code.md) · [Clients and gateways](../../concepts/clients-and-gateways.md)
