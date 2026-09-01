# ADR-0004: Agent tool-call compatibility

Date: 2026-06-15  
Status: **accepted** (amended 2026-08-28 — G1b / #269: prefix L1 for agent turns)

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
| Agent turn + L0 miss | Route to **L3** (capability / profile may pick L4/L5). **Do not** attempt Lt or L2. |
| Agent turn + client defines `tools` | daari does **not** replace client tool execution — it routes the *completion* request only |
| Identical full history + tools schema | **L0 hit** — same completion as the first turn |
| Last `tool` message changed | **L0 miss** — key includes that payload; do not serve the prior answer |

**Rationale:** Agent tool loops are stateful. daari optimizes the LLM completion leg, not the client's tool runner. The stable prefix is most of the tokens; skipping cache on every `tools` request turned the product off for Cursor.

### 3. Cache policy for agent turns

| Case | L0 exact | L1 semantic |
|------|----------|-------------|
| Simple chat (no tools, no tool_calls) | ✅ Normal cache key | ✅ Cosine + verification |
| Agent turn, identical messages + tools | ✅ **On by default** (full message hash + tools schema) | ✅ **Prefix L1** — cosine over the stable prefix, tool-result suffix matched exactly |
| Agent turn, last tool result changed | ❌ Different key | ❌ Skip — different suffix hash, the prior answer is never served |
| `X-Daari-No-Cache: true` | ❌ | ❌ |

**Cache key components:**
```
hash(messages including tool role + tool_calls) + model + temperature + hash(tools) + sampling fingerprint
```

**Prefix-L1 key components (G1b):**
```
cosine(system + tools + history minus trailing tool results) within context: model + temperature + hash(tools) + hash(trailing tool results)
```

The original “skip L0 by default / opt-in `X-Daari-Cache-Agent`” policy is withdrawn. Exact-repeat of the *full* agent request is safe because the last tool payload is in the key. Semantic L1 now runs over the *stable prefix* only: the trailing tool results are hashed into the lookup context, so a changed last tool result can never cosine-match the previous final answer. Turns that emit tool calls are still never stored as answers.

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
- Identical agent turns are $0 (L0); a changed tool result cannot replay the prior answer
- Lt / L2 still never fire on an agent protocol turn

**Negative**
- L1 for agent turns is prefix-scoped: a changed prefix wording can hit, a changed tool result cannot
- Local models without tool-call support force L6 more often
- Anthropic SSE path does not yet share the OpenAI-stream L0 lookup

## MVP implementation checklist

- [x] Detect agent turn from payload
- [x] Exact L0 on for identical agent turns; miss when the last tool result changes (G1 / #223)
- [x] Include `tools_schema_hash` in cache key
- [x] Prefix L1 for agent turns; miss on suffix (G1b / #269)
- [ ] Log `agent_turn: true` in daari_meta
- [ ] Test GP-18 in routing eval set
