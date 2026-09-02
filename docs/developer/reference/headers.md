# Request headers

| Header | Effect |
|--------|--------|
| `Authorization: Bearer` / `x-api-key` | API key or virtual key |
| `X-Daari-Meta: true` | Embed `daari_meta` in JSON responses |
| `X-Daari-No-Cache` | Skip L0/L1 |
| `X-Daari-Tier-Override` | Force a tier |
| `X-Daari-Tier-Cap` | Cap local tier (e.g. `L3`) |
| `X-Daari-No-Frontier` | Forbid L6 |
| `X-Daari-Latency-Budget` | Max local latency (ms) |
| `X-Daari-Client-Id` | Ledger attribution |
| `X-Daari-Project` | Path for `.daari.yaml` discovery |
| `X-Daari-Boundary-Profile` | Named `boundaries.profiles` overlay for this request (browser extension site profiles) |
| `X-Daari-Tools` | Tool-related client hints |
| `X-Daari-Confirm*` / `X-Daari-ReRun-Command` | Lt ask-gate confirmation |

Explicit headers win over project profiles and most config defaults.

# Response headers

`/v1/chat/completions` and `/v1/messages` report cost and routing on every
response so FinOps and observability tooling can scrape headers instead of
bodies. Values agree with `daari_meta` on the same response.

| Header | Value |
|--------|-------|
| `x-daari-response-cost` | USD actually spent on this response. `0` for every local tier (L0–L5, Lt, L2, CCS); for L6 the provider-reported `usage.cost` when present, otherwise `pricing.models` × reported tokens (flat `usage.frontier_price_per_1k_tokens` fallback). |
| `x-daari-response-cost-avoided` | Frontier-implied USD for a response served locally for $0: `(prompt_chars + completion_chars) / 4` tokens at `usage.frontier_price_per_1k_tokens` — the same basis as `daari report`'s `estimated_saved_usd`. `0` for L6. |
| `x-daari-tier` | Serving tier (`L0`, `L1`, `L3` … `L6`, `Lt`, `L2`, `CCS`). Same as `daari_meta.tier`. |
| `x-daari-cache` | `hit` (L0/L1 served the answer), `draft` (an L1 near-miss steered generation), or `miss`. |

Values are plain decimal strings (`0`, `0.0004`), never scientific notation.

## Streaming contract

Headers must leave before the first byte, so streams report only what the
router knows by then:

- `x-daari-tier` and `x-daari-cache` are sent whenever the first real chunk is
  ready before the keepalive interval (`server.sse_keepalive_seconds`). Cache
  hits, deterministic tiers and buffered local tiers always qualify; a model
  whose first chunk arrives after the interval gets its headers on the
  keepalive frame, without tier or cache.
- `x-daari-response-cost` and `x-daari-response-cost-avoided` are **never**
  sent on streams — usage is unknown until the last chunk. Use the ledger
  (`daari report`, `/v1/daari/report`) for streamed spend.
