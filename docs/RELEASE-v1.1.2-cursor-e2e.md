# Release notes — v1.1.2 (Cursor BYOK E2E)

> Date: 2026-06-23  
> Scope: Cursor IDE Ask mode via OpenAI-compatible BYOK + cloudflared tunnel → local daari → Ollama

## Summary

Cursor **Ask + daari** model now works end-to-end: requests from Cursor cloud reach daari through an HTTPS tunnel, route to local Ollama, and return streamed text in the UI. Previously, responses were empty due to message-format, tool-call, and streaming-tier bugs.

## What was fixed

| Area | Change |
|------|--------|
| **Message content** | `daari/gateway/content.py` — normalize string, array, dict, `text`, `input_text`, `output_text` blocks |
| **Cursor tools** | Strip 18 IDE tools on BYOK Ask requests; inject plain-text system hint |
| **History sanitization** | Remove `tool_calls` from messages before Ollama when tools stripped |
| **Streaming tiers** | L4/L5→L3 fallback in `stream_openai_chunks()` (parity with non-stream `route()`) |
| **OpenAI compat** | `/v1/models`, SSE headers, usage chunk, client model name `daari`, optional `X-Daari-Meta` |
| **Debug logging** | `~/.daari/cursor-requests.log` — request shape, tier attempts, `content_chunks` |
| **Tunnel** | Hardened `scripts/tunnel.sh` health probe and hostname parsing |

## Testing

### Automated (CI)

```bash
pytest -m "not integration and not benchmark"
# 162 passed, 1 skipped (2026-06-23)
```

New/updated tests:

- `tests/unit/test_gateway_content.py` — content normalization + Ollama sanitization
- `tests/integration/test_gateway_flow.py` — Cursor-shaped payloads (18 tools, `input_text`, L4 fallback, stream usage)
- `tests/conftest.py` — `mock_all_ollama_executors`, `META_HEADERS`, `MOCK_MODEL_CONTENT`

### Manual E2E (verified 2026-06-23)

| Step | Result |
|------|--------|
| `daari serve` (venv) + `cloudflared` tunnel | ✅ |
| Cursor Settings: BYOK URL = `https://…trycloudflare.com/v1`, model `daari` | ✅ |
| Ask: "what is two plus two?" | ✅ Answer from local Ollama |
| Log: `content_chunks` > 0, `user_agent: Cursor/1.0` | ✅ |
| L4 fallback when `llama3.1:8b` missing | ✅ `stream_fallback_ok` → L3 |
| L4 direct when model pulled | ✅ |

Example healthy log tail:

```json
{"event": "tools_stripped", "count": 18}
{"event": "stream_attempt", "tier": "L3", "ollama_model": "llama3.2:3b"}
{"event": "chat_completions_stream_done", "content_chunks": 24}
```

## Known limitations

1. **Tool hallucination on follow-ups** — Cursor system prompt still describes IDE tools after daari strips them; small local models may narrate fake tool use (`ls @src`, etc.).
2. **Ask-only tool stripping** — Agent mode with real tool round-trip not yet implemented (see ADR-0004).
3. **Long context → L4** — Cursor context user message (>250 words) routes to L4; pull `llama3.1:8b` or accept L3 fallback latency.
4. **Tunnel required** — Cursor cloud blocks private IPs; localhost only works for curl/extension, not Cursor BYOK.

## Addendum — everything else in v1.1.2 (2026-07-11)

Between the Cursor E2E fix above and the tag, the autonomous dev loop shipped
20+ additional changes. All were TDD'd, CI-gated, auto-merged, and validated
E2E by the local watchdog against live Ollama.

### Routing and intelligence

- Ask vs Agent BYOK split with real tool round-trip passthrough (#12, ADR-0004)
- Prompt profile: category + complexity heuristics with per-category action
  policies (`routing.category_policies`) (#23)
- Tier cap via `routing.max_tier_for_chat` config or `X-Daari-Tier-Cap` header (#28)
- Context optimizer: history trimming + whitespace squeeze for local models (#26)
- Frontier prompt slimming before L6 escalation (#37)
- Frontier daily budget guard with local-only fallback (#18)

### Caching

- L0 exact cache on the streaming path (#16)
- L1 near-miss answers injected as drafts for generation (#25)
- L0/L1 TTLs, category TTL overrides, `daari cache prune` (#39)
- Org shared cache: paraphrase matching by vector similarity (#31)

### Observability

- Persistent usage ledger with savings report (`daari report`) (#17)
- Per-request decision traces, retrievable by id (`daari trace`) (#24)
- Markdown export for reports and traces (`--format markdown --out`) (#38)

### Gateway and setup

- Anthropic stream parity: tier fallback, sanitization, usage estimates (#30)
- Explicit no-tools hint leads stripped-tools requests (#11)
- `daari setup cursor` pulls the L4 model; doctor severity upgrades (#29)

### Automation and CI

- Autonomous dev loop: agent contract (AGENTS.md), local watchdog, cloud
  automations — see [AUTOMATION.md](AUTOMATION.md)
- Browser extension DOM test suite in CI (#33)
- CI expanded to four required checks: test, extension, lint, sanity (#41)

## Next steps

Backlog is tracked as GitHub issues labeled `auto-dev`; the scout automation
files new ones. See [TRACKING.md](TRACKING.md) for full history.
