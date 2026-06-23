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

## Next steps (planned)

| Priority | Task |
|----------|------|
| High | Ask vs Agent BYOK split — strip tools for Ask only |
| Medium | Stronger anti-tool-hallucination system prompt for Cursor BYOK |
| Medium | Cursor-specific tier cap or profile (optional L3-only for latency) |
| Low | Tag v1.1.2 on PyPI after soak period |
| Low | Automated Cursor cloud E2E (manual only today) |

See [TRACKING.md](TRACKING.md#cursor-e2e-byok--poc-2026-06-23) for full tracker.
