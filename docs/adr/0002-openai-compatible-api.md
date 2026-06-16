# ADR-0002: OpenAI-compatible API as primary integration surface

Date: 2026-06-15  
Status: **accepted**

## Context

daari must work with Cursor, Claude Code, arbitrary CLIs, SDKs, IDEs, and future UIs with **minimal change** per tool. We need a primary wire protocol that maximizes compatibility on day one.

## Decision

Expose **OpenAI-compatible HTTP API** as the **first gateway adapter** for MVP (Phase A). It is **not** daari's permanent or exclusive identity.

Architecture is **pluggable gateways** — see [ADR-0007](0007-pluggable-gateway-adapters.md). Additional adapters (Anthropic, MCP, daari-native) attach to the same internal router without rewriting core logic.

## Rationale

| Factor | Why OpenAI-compat wins |
|--------|------------------------|
| Ecosystem | Ollama, LiteLLM, LocalAI, vLLM already use it — daari slots into existing stacks |
| Cursor / Claude Code | Configurable via base URL; no plugin required |
| SDK reuse | OpenAI client libraries work with `base_url` override |
| Minimal change | Users change one setting, not client code |
| Scope | Custom API per tool would explode integration work |

**Important:** "OpenAI-compatible" describes the **wire format**, not the provider. daari routes internally to cache, tool-native executors, Ollama, or frontier — not to OpenAI by default.

## Consequences

**Positive**
- Fast path to universal tool support
- Setup recipes are mostly "point base_url at localhost"
- Existing scripts and agents work unchanged

**Negative**
- Routing metadata is not first-class in the standard schema — use `daari_meta` extensions + logs
- Anthropic-native clients may need a compat shim or second gateway (Phase C)
- Some agent tool-call edge cases may need passthrough tuning

## Related

- Setup module: `daari setup <tool>` recipes per client
- PRD § Integration strategy
