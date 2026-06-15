# ADR-0004: Agent tool-call compatibility

Date: 2026-06-15  
Status: **accepted**

## Context

Cursor, Claude Code, and other agents send OpenAI-compat requests with:

- `tools` — function definitions in the request
- `tool_calls` — in assistant messages (multi-turn)
- `tool` role messages — results fed back

daari must route, cache, and respond without breaking agent loops. Plan review issue #5.

## Decision

### 1. Agent-turn detection

A request is an **agent turn** if any of:

- `tools` array is non-empty in the request body
- Any message in `messages` has `tool_calls` field
- Any message has `role: "tool"`

### 2. Routing for agent turns

| Condition | Behavior |
|-----------|----------|
| Agent turn + MVP (Phase A) | Route to **L3** (or L0 if exact repeat of full message history). **Do not** attempt Lt or L2. |
| Agent turn + client defines `tools` | daari does **not** replace client tool execution — it routes the *completion* request only |
| `tool_calls` in latest assistant msg | Passthrough execution at same tier as prior turn; no L0 cache read |

**Rationale:** Agent tool loops are stateful. daari optimizes the LLM completion leg, not the client's tool runner.

### 3. Cache policy for agent turns

| Case | L0 cache |
|------|----------|
| Simple chat (no tools, no tool_calls) | ✅ Normal cache key |
| Agent turn (tools defined or tool history) | ❌ **Skip L0 read/write** by default |
| Agent turn + `X-Daari-Cache-Agent: true` | ✅ Opt-in cache with full message hash + tools_schema_hash |

**Cache key components (when cacheable):**
```
hash(messages) + model + temperature + hash(tools) + hash(tool_choice)
```

### 4. Streaming + tool_calls

- Stream model responses **transparently** from Ollama/frontier
- daari does not buffer/reparse tool_calls mid-stream in MVP
- If local model lacks native tool-call format → **escalate to L6** (Phase A.1) or return error with `daari_meta.error: "tool_calls_unsupported_locally"`

### 5. Lt dispatch and agent turns

**Lt is never invoked** during an active agent turn (tools in context). Tool-native tier applies only to **direct user chat** without agent tool schema.

### 6. Response shape

When daari handles an agent completion, response must preserve OpenAI-compat fields:

- `choices[].message.content`
- `choices[].message.tool_calls` (if model supports)
- `finish_reason`

Add `daari_meta` as sibling field in response body (non-standard extension clients ignore).

## Consequences

**Positive**
- Predictable behavior for Cursor agent mode
- Avoids corrupt cache hits mid-tool-loop
- Clear MVP scope: optimize non-agent and simple completions first

**Negative**
- Agent sessions benefit less from L0 cache unless opt-in
- Local models without tool-call support force L6 more often
- Full agent-aware routing deferred to v2

## MVP implementation checklist

- [ ] Detect agent turn from payload
- [ ] Skip L0 when agent turn detected
- [ ] Include `tools_schema_hash` in cache key when caching enabled
- [ ] Log `agent_turn: true` in daari_meta
- [ ] Test GP-18 in routing eval set
