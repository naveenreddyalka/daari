# Clients and gateways

**Outcome:** Know which wire protocol each client uses and how it reaches `Router.route()`.

## Surfaces (same daemon, `:11435`)

| Surface | Paths | Typical client |
|---------|-------|----------------|
| OpenAI Chat | `POST /v1/chat/completions` | Cursor BYOK, VS Code, SDKs |
| OpenAI Responses | `POST /v1/responses` | Newer OpenAI SDKs |
| Anthropic | `POST /v1/messages`, `POST /v1/messages/count_tokens` | Claude Code |
| Ollama facade | `/api/chat`, `/api/tags`, … | JetBrains AI Assistant |
| MCP | `POST /mcp` (JSON-RPC 2.0), `POST /v1/mcp/query` (deprecated) | Cursor, Claude Desktop |

Adapters convert to `InternalRequest` / `InternalResponse` ([internals](../internals/request-lifecycle.md)).

## One-click setup

```bash
daari setup cursor --tunnel
daari setup claude-code
daari setup intellij
daari setup vscode
daari setup openai-compat
```

## Sampling parameters

Generation controls are read on every surface and mapped to the backend: `max_tokens`
(`max_completion_tokens`, `max_output_tokens`, or `num_predict` depending on the
surface), `top_p`, `top_k`, `stop` / `stop_sequences`, `seed`, `frequency_penalty`,
and `response_format: json_object`. Omitted parameters are not sent, so backend
defaults stand.

What a local model cannot do is reported in `daari_meta.warning` rather than silently
dropped: `presence_penalty`, `n > 1`, `logprobs`, and `tool_choice: required`.
`frequency_penalty` is approximated by Ollama's `repeat_penalty`. Sampling parameters
are part of the cache key, so a 16-token answer is never served to a request asking
for 500.

Image parts (`image_url`, Anthropic `image` sources, Ollama `images`) ride on
`Message.images`. A vision request is forwarded to a vision-capable tier, or the
gateway returns **422** — it never strips the image and answers as if the question
were text-only.

`POST /v1/embeddings` is served by the same embedder L1 already uses, so a client
pointed at daari does not need a second host for vectors.

`POST /v1/messages/count_tokens` is a local estimate (`estimate_tokens` on system +
messages + tools), not an L6 round-trip. When L6 itself is Anthropic (`provider`
`anthropic`/`claude`, or `anthropic.com` in `base_url`), the frontier executor POSTs
native `/v1/messages` with `x-api-key` / `anthropic-version` headers, not an OpenAI
body at `/chat/completions`. Prompt-cache hints land on the last system block as
`cache_control: ephemeral`.

`POST /mcp` is a JSON-RPC 2.0 MCP server (streamable HTTP): `initialize`,
`tools/list`, `tools/call`. Tools are `route`, `stats`, and whatever integration
providers are registered (Sourcegraph, GHE, GitLab, configured MCP egress). Auth is
the same Bearer / `x-api-key` middleware as the rest of the daemon.
`POST /v1/mcp/query` still works and sends a `Deprecation` header pointing at `/mcp`.

## Auth

Optional `server.api_key`, virtual keys (`daari keys`), or SSO for admin surfaces. Health stays open when keyed.

## Next

→ [Cursor guide](../guides/clients/cursor.md) · [MCP](../guides/clients/mcp.md) · [HTTP API](../reference/http-api.md)
