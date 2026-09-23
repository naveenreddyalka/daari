# Request headers

| Header | Effect |
|--------|--------|
| `Authorization: Bearer` / `x-api-key` | API key or virtual key |
| `X-Daari-Meta: true` | Embed `daari_meta` in JSON responses |
| `X-Daari-No-Cache` | Skip L0/L1 |
| `X-Daari-Tier-Override` | Force a tier |
| `X-Daari-Tier-Cap` | Cap local tier (e.g. `L3`). Beats body `cost_tier`. |
| `X-Daari-No-Frontier` | Forbid L6 |
| `X-Daari-Latency-Budget` | Max local latency (ms) |
| `X-Daari-Deadline-Ms` | Wall-clock budget for the whole request (ms). Wins over `upstream.request_deadline_seconds`. Honored on chat (`/v1/chat/completions`, Anthropic, Responses), Ollama facade (`/api/chat`, `/api/generate`), audio (`/v1/audio/transcriptions`, `/v1/audio/translations`, `/v1/audio/speech`), embeddings (`/v1/embeddings`), and MCP `tools/call`. When spent, the gateway returns **504** with `request_deadline_exceeded` and does not escalate further. On streaming responses the budget applies to time-to-first-token only. |
| `X-Daari-Client-Id` | Ledger attribution |
| `X-Daari-Project` | Path for `.daari.yaml` discovery |
| `X-Daari-Boundary-Profile` | Named `boundaries.profiles` overlay for this request (browser extension site profiles) |
| `X-Daari-Tools` | Tool-related client hints |
| `X-Daari-Confirm*` / `X-Daari-ReRun-Command` | Lt ask-gate confirmation |
| `X-Request-ID` | Correlation id: sanitized inbound value or a generated 16-char hex id. Echoed on every gateway response (chat, Anthropic Messages, Responses, Ollama facade, embeddings, audio) and forwarded on upstream hops (Ollama, OpenAI-compat, MLX, frontier, ASR, TTS, embeddings, MCP egress) as `X-Request-ID`. |
| `Idempotency-Key` | Replay-safe retries for `POST /v1/chat/completions` and `POST /v1/responses` (stream and non-stream). Scoped to the authenticated principal (virtual key id, or master/anonymous). Same key + same body hash within `idempotency.ttl_seconds` (default 24h) returns the original status/body without calling the router again. Same key + different body returns **409** `idempotency_conflict`. In-flight duplicates wait for the first request (bounded by `idempotency.wait_seconds`). Missing header is a no-op. |

Explicit headers win over project profiles and most config defaults.

# Response headers

`/v1/chat/completions` and `/v1/messages` report cost and routing on every
response so FinOps and observability tooling can scrape headers instead of
bodies. Values agree with `daari_meta` on the same response.

| Header | Value |
|--------|-------|
| `x-daari-response-cost` | USD actually spent on this response. `0` for every local tier (L0–L5, Lt, L2, CCS); for L6 the provider-reported `usage.cost` when present, otherwise `pricing.models` × reported tokens (flat `usage.frontier_price_per_1k_tokens` fallback). |
| `x-daari-response-cost-avoided` | Frontier-implied USD for a response served locally for $0: `(prompt_chars + completion_chars) / 4` tokens at `usage.frontier_price_per_1k_tokens` — the same basis as `daari report`'s `estimated_saved_usd`. `0` for L6. |
| `x-daari-session-cost-avoided` | Running sum of `x-daari-response-cost-avoided` for the `X-Daari-Session` id, TTL matching `routing.session_affinity_ttl_seconds` (default 30m). Omitted when the client sends no session id. With `cache.backend: redis`, the accumulator is fleet-shared (same Redis as pins); otherwise it is per-process. |
| `x-daari-tier` | Serving tier (`L0`, `L1`, `L3` … `L6`, `Lt`, `L2`, `CCS`). Same as `daari_meta.tier`. |
| `x-daari-cache` | `hit` (L0/L1 served the answer), `draft` (an L1 near-miss steered generation), or `miss`. |
| `x-daari-warning` | Human-readable soft warning (sampling knobs the local tier could not honor, budget soft-band, etc.). Always set when `daari_meta.warning` is set — no `X-Daari-Meta` opt-in required. |
| `x-daari-dropped-params` | Comma-separated client parameter names the serving tier could not honor (e.g. `logprobs,store`). Omitted when nothing was dropped. Same info as the sampling half of `x-daari-warning`, machine-readable. |

Values are plain decimal strings (`0`, `0.0004`), never scientific notation.

## Budget headers

Requests authenticated with a virtual key that has at least one budget window
(its own or inherited from its team) also report how much frontier budget is
left, so clients and FinOps tooling can self-throttle to $0 local tiers before
the `402`. Only the **tightest** window is reported: the one with the least USD
remaining across key and team scopes.

| Header | Value |
|--------|-------|
| `x-daari-budget-remaining` | USD left in the tightest window (`0` when exhausted). Same decimal format as the cost headers. |
| `x-daari-budget-limit` | That window's cap in USD. |
| `x-daari-budget-window` | Window duration: `1d`, `1mo`, or the configured `7d` / `12h`. |
| `x-daari-budget-reset` | Epoch seconds when the window resets — the same instant as the `402` body's `reset_at`. |
| `x-daari-budget-scope` | `key` or `team` — which cap is the tightest. |
| `x-daari-budget-warning` | `soft` when USD spend/limit ≥ `frontier.soft_budget_ratio` but under the hard cap (#626). Omitted otherwise (and on hard `402`). |
| `x-daari-quota-requests-remaining` | Billable requests left in the tightest request-count window (`0` when exhausted). |
| `x-daari-quota-requests-limit` | That window's request cap. |
| `x-daari-quota-requests-warning` | `soft` when used/cap ≥ `frontier.soft_budget_ratio` but under the hard cap (#498). Omitted otherwise. |
| `x-daari-ratelimit-warning` | `soft` when RPM/TPM usage ≥ `frontier.soft_budget_ratio` but under the hard cap (#518). Omitted on hard `429`. |
| `X-RateLimit-Scope` | `key` / `team` / `model` — which rate-limit counter was tightest on this response (also on hard `429`). |

Rules:

- Sent on every 2xx from an authenticated route, streaming included: budget
  state is known before the first byte, unlike per-response cost.
- A budget-exhausted `402` (`budget_exceeded`) carries the same five headers
  with remaining `0`, plus `Retry-After` in seconds until the reset — the same
  shape as the rate-limit `429`. Request-quota `402`s carry the
  `x-daari-quota-requests-*` pair instead of the USD remaining/limit headers
  (window / reset / scope still apply).
- No budget window for the caller ⇒ none of these headers. Master-key and
  open single-user installs are unchanged.
- Only frontier (L6) spend counts toward USD `remaining`; local tiers and cache
  hits are free for USD. Request quotas count every non-cache serve (local +
  frontier); L0/L1 cache hits do not consume request quota.

## Idempotency-Key

Safe client retries for chat completions and Responses. Scope is the
authenticated principal plus the header value; records expire after
`idempotency.ttl_seconds` (default 86400) and are deleted by `daari prune`.

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer $DAARI_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: deploy-rollout-42" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"ping"}]}'
```

A second identical request with the same key returns the same JSON without
another router call. Changing the body while reusing the key returns **409**
`idempotency_conflict`.

## Streaming contract

Headers must leave before the first byte, so streams report only what the
router knows by then:

- `x-daari-tier` and `x-daari-cache` are sent whenever the first real chunk is
  ready before the keepalive interval (`server.sse_keepalive_seconds`). Cache
  hits, deterministic tiers and buffered local tiers always qualify; a model
  whose first chunk arrives after the interval gets its headers on the
  keepalive frame, without tier or cache.
- `x-daari-response-cost` and `x-daari-response-cost-avoided` are **never**
  sent on streams — usage is unknown until the last chunk. The final OpenAI
  usage chunk and Anthropic `message_delta.usage` carry `cost` (USD; `0` local,
  L6 from `cost_usd()` / provider `usage.cost`). When `X-Daari-Session` is set
  and `stream_options.include_usage` is on, the same chunk also carries
  `session_cost_avoided` (running local-first savings for that session). OpenAI
  usage also always includes `prompt_tokens_details.cached_tokens` (`0` when
  unknown; L0/L1 hits set it equal to `prompt_tokens`; L6 uses provider meta).
  Anthropic adds `cache_read_input_tokens` only when that figure is known and
  non-zero (native field — safe for clients). Use the ledger
  (`daari report`, `/v1/daari/report`) for aggregates.
- The `x-daari-budget-*` headers **are** sent on streams; they describe the
  caller's budget before this request, not this request's cost.
