# ADR-0007: Pluggable gateway adapters (not tied to OpenAI)

Date: 2026-06-15  
Status: **accepted**

## Context

daari uses OpenAI-compatible HTTP for MVP ([ADR-0002](0002-openai-compatible-api.md)). The product principle says compat is an **adapter, not identity** — we must not become permanently coupled to OpenAI's wire format if other protocols gain adoption (Anthropic Messages API, MCP, future standards).

## Decision

Architect daari with a **pluggable gateway layer**:

```
Client (any wire format)
        │
        ▼
┌───────────────────┐
│  Gateway adapter  │  ← OpenAI, Anthropic, MCP, daari-native, …
│  (translate in)   │
└─────────┬─────────┘
          │ InternalRequest (canonical)
          ▼
┌───────────────────┐
│  Router + tiers   │  ← single brain; format-agnostic
└─────────┬─────────┘
          │ InternalResponse (canonical)
          ▼
┌───────────────────┐
│  Gateway adapter  │
│  (translate out)  │
└───────────────────┘
```

**Rules:**

1. **Router never speaks OpenAI JSON** — only an internal canonical request/response model.
2. **Each wire format is an adapter** — add/remove without changing routing logic.
3. **OpenAI-compat is adapter #1** for MVP — because ecosystem adoption today, not because it's sacred.
4. **New adapters ship when client demand justifies them** — not before.
5. **No adapter is required at runtime** — enable in config; all can listen on different ports or paths.

## Adapter roadmap

| Adapter | Wire format | Priority | Phase | Clients |
|---------|-------------|----------|-------|---------|
| **openai** | `POST /v1/chat/completions` | P0 | A | Cursor, OpenAI SDK, curl |
| **anthropic** | Messages API | P1 | C2 | Claude Code, Claude SDK |
| **mcp** | MCP protocol | P2 | C1 | MCP-native agents |
| **daari** | daari-native REST | P3 | C1+ | Future UI, rich routing metadata |
| **future** | Whatever gains adoption | P4 | TBD | New tools as ecosystem shifts |

If a new format becomes dominant, we **add an adapter** — we do not rewrite the router or rebrand daari as "OpenAI-only."

## Internal canonical model (sketch)

Adapters translate to/from:

```python
# Conceptual — not implementation yet
InternalRequest:
  messages: list[Message]
  tools: list[Tool] | None
  stream: bool
  metadata: RequestMeta  # client id, agent_turn flag, headers

InternalResponse:
  content: str | None
  tool_calls: list[ToolCall] | None
  daari_meta: DaariMeta   # tier, cache_hit, latency, …
```

All tiers (L0–L6, Lt) consume `InternalRequest` and produce `InternalResponse`.

## Consequences

**Positive**
- Not locked to OpenAI if ecosystem moves
- Anthropic/MCP become additive, not rewrites
- Clear boundary for tests: mock `InternalRequest` → expect tier

**Negative**
- Translation layer is extra code upfront (minimal for OpenAI-only MVP)
- Must maintain adapters as upstream APIs evolve

## MVP scope

Phase A implements **openai adapter only**, but file layout must allow:

```
daari/gateway/
  base.py          # GatewayAdapter protocol
  openai.py        # Phase A
  anthropic.py     # stub / Phase C2
  internal.py      # InternalRequest/Response types
```

## Related

- [ADR-0002](0002-openai-compatible-api.md) — first adapter, not only adapter
- [ROADMAP.md](../prd/ROADMAP.md) — adapter phases
