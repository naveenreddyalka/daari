# Clients and gateways

**Outcome:** Know which wire protocol each client uses and how it reaches `Router.route()`.

## Surfaces (same daemon, `:11435`)

| Surface | Paths | Typical client |
|---------|-------|----------------|
| OpenAI Chat | `POST /v1/chat/completions` | Cursor BYOK, VS Code, SDKs |
| Audio | `POST /v1/audio/transcriptions`, `POST /v1/audio/speech` | OpenAI speech-to-text / text-to-speech clients |
| OpenAI Responses | `POST /v1/responses`, `POST /v1/responses/input_tokens`, `GET /v1/responses/{id}`, `POST /v1/responses/{id}/cancel`, `DELETE /v1/responses/{id}` | Newer OpenAI SDKs |
| Anthropic | `POST /v1/messages`, `POST /v1/messages/count_tokens` | Claude Code, Claude Desktop (gateway mode) |
| Ollama facade | `/api/chat`, `/api/generate`, `/api/embed`, `/api/tags`, … | JetBrains AI Assistant, ChatGPT Desktop |
| MCP | `POST /mcp` (JSON-RPC 2.0), `POST /v1/mcp/query` (deprecated) | Cursor, Claude Desktop |

Adapters convert to `InternalRequest` / `InternalResponse` ([internals](../internals/request-lifecycle.md)).

## One-click setup

```bash
daari setup cursor --tunnel
daari setup claude-code
daari setup claude-desktop
daari setup intellij
daari setup vscode
daari setup openai-compat
```

## Sampling parameters

Generation controls are read on every surface and mapped to the backend: `max_tokens`
(`max_completion_tokens`, `max_output_tokens`, or `num_predict` depending on the
surface), `top_p`, `top_k`, `stop` / `stop_sequences`, `seed`, `frequency_penalty`,
and `response_format: json_object`. Agent SDKs also send `parallel_tool_calls`,
`logit_bias`, and `top_logprobs` — those reach frontier / OpenAI-compat executors
via `openai_payload()` and split the L0 cache fingerprint when set. Omitted
parameters are not sent, so backend defaults stand.

What a local model cannot do is reported in `daari_meta.warning` rather than silently
dropped: `presence_penalty`, `n > 1`, `logprobs`, `top_logprobs`, `logit_bias`,
`parallel_tool_calls`, and `tool_choice: required`.
`frequency_penalty` is approximated by Ollama's `repeat_penalty`. Sampling parameters
are part of the cache key, so a 16-token answer is never served to a request asking
for 500.

Image parts (`image_url`, Anthropic `image` sources, Ollama `images`) ride on
`Message.images`. A vision request is forwarded to a vision-capable tier, or the
gateway returns **422** — it never strips the image and answers as if the question
were text-only.

OpenAI `input_audio` parts ride on `Message.audio`. They are rebuilt on the L6
OpenAI payload. When `asr.base_url` is set, daari also transcribes each clip and
injects the text into the local-tier prompt; see
[local speech-to-text](../guides/backends/asr.md#chat-input_audio-blocks).

`POST /v1/embeddings` is served by the same embedder L1 already uses, so a client
pointed at daari does not need a second host for vectors.

`POST /v1/audio/transcriptions` accepts the OpenAI multipart form and forwards
it to `asr.base_url` when that is set. With no local ASR the route returns
**501**. `asr.frontier_fallback` defaults to false, so the file is never sent
to a cloud endpoint unless you turn that flag on. See
[local speech-to-text](../guides/backends/asr.md).

`POST /v1/audio/speech` accepts the OpenAI JSON speech body and forwards it to
`tts.base_url` when that is set. With no local TTS the route returns **501**.
See [local text-to-speech](../guides/backends/tts.md).

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

The Responses surface round-trips `function_call` / `function_call_output` items,
chains turns with `previous_response_id`, honors `store: false`, and returns
`queued` for `background: true` (poll `GET /v1/responses/{id}`).
`POST /v1/responses/{id}/cancel` is idempotent: an in-flight background job
stops writing tokens and the stored status becomes `cancelled`; an already
terminal object returns 200 with its current body. `DELETE /v1/responses/{id}`
removes the row so a later GET is 404. Tenancy matches GET (other virtual keys
see 404, not 403; the master key can cancel or delete any row). `include` is
rejected with 400 rather than ignored; `metadata` is echoed.
Responses-native sampling maps onto the same `SamplingParams` as chat:
`reasoning.effort` → `reasoning_effort`, `text.format` → JSON / `json_schema`
(including `name`/`strict`), plus `tool_choice`, `parallel_tool_calls`, and
`service_tier`. Unsupported `truncation` is logged (`responses_truncation_ignored`)
rather than 422'd.
`POST /v1/responses/input_tokens` is a local estimate (`estimate_tokens` on
instructions + input messages + tools), matching Anthropic
`/v1/messages/count_tokens` — not an L6 round-trip.

## Auth

Optional `server.api_key`, virtual keys (`daari keys`), or SSO for admin surfaces. Health stays open when keyed.

## Next

→ [Cursor guide](../guides/clients/cursor.md) · [MCP](../guides/clients/mcp.md) · [HTTP API](../reference/http-api.md)
