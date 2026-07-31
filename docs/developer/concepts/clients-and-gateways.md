# Clients and gateways

**Outcome:** Know which wire protocol each client uses and how it reaches `Router.route()`.

## Surfaces (same daemon, `:11435`)

| Surface | Paths | Typical client |
|---------|-------|----------------|
| OpenAI Chat | `POST /v1/chat/completions` | Cursor BYOK, VS Code, SDKs |
| OpenAI Responses | `POST /v1/responses` | Newer OpenAI SDKs |
| Anthropic | `POST /v1/messages` | Claude Code |
| Ollama facade | `/api/chat`, `/api/tags`, … | JetBrains AI Assistant |
| MCP ingress | `POST /v1/mcp/query` | MCP hosts |

Adapters convert to `InternalRequest` / `InternalResponse` ([internals](../internals/request-lifecycle.md)).

## One-click setup

```bash
daari setup cursor --tunnel
daari setup claude-code
daari setup intellij
daari setup vscode
daari setup openai-compat
```

## Auth

Optional `server.api_key`, virtual keys (`daari keys`), or SSO for admin surfaces. Health stays open when keyed.

## Next

→ [Cursor guide](../guides/clients/cursor.md) · [HTTP API](../reference/http-api.md)
