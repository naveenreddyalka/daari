# daari vs LiteLLM

LiteLLM is a **provider gateway**: one OpenAI-shaped API in front of 100+ cloud models. daari is a **local cost optimizer**: cache, tools, and Ollama/MLX first, frontier last.

| | LiteLLM | daari |
|--|---------|-------|
| Job | Talk to many remote providers | Keep repeat agent work on your machine |
| Default path | Cloud / configured backends | L0/L1 cache → tools → local → L6 |
| Cache | Optional Redis/Qdrant | Built-in exact + semantic, measured false-hit rate |
| IDE setup | DIY | `daari setup cursor` / Claude Code / JetBrains / VS Code |
| License | MIT-class (OSI) | Apache 2.0 (OSI) |
| Stars / mindshare | Category default | New |

**Pick LiteLLM** if you need 100 providers and virtual keys across a team.

**Pick daari** if Cursor or Claude Code is burning frontier tokens on work a cache or a 3B local model can do, and you want that path to be the default.

They can stack: daari for local $0 tiers, LiteLLM (or OpenRouter) as one L6 slot.

## LiteLLM 1.104 GA (local parity)

LiteLLM [v1.104.0](https://docs.litellm.ai/release_notes/v1.104.0/v1-104-0)
(3 Oct 2026) tightened a few gateway gates. daari already matches these
**on-device** without sending transcripts off-box:

| LiteLLM 1.104 | daari today |
|---------------|-------------|
| Refuse weak/unset master key at start | Same: refuse weak/unset master key (sandbox hatch for local demos) |
| Native compact-to-fit across conversation APIs | Opt-in `routing.compact_to_fit` trims droppable turns before L6; successful trims record `tokens_before` / `tokens_after` on-device (stats/Prometheus: `compact_to_fit_tokens_dropped`) |
| MCP key grant / tool permissions (`require_key_mcp_access_defined`) | Opt-in `integrations.mcp_policy.require_key_access_defined` fail-closed when the virtual key has no MCP grant |

**stdio MCP off by default** in LiteLLM is N/A for daari today (no stdio MCP
transport); watch if a buyer asks. A2A and admin UI stay demand-triggered.

## LiteLLM 1.105 RC (watch)

LiteLLM [v1.105.0-rc.1](https://github.com/BerriAI/litellm/releases)
(4 Oct 2026) is **prerelease**. Do not treat it as the comparison floor —
**1.104.0 GA** above is still the stable bar. The RC advertises a Microsoft 365
MCP catalog, Straiker v3 fail-closed routing, and Lens / `litellm.agent()`
traces. daari does **not** ship those RC items; this page only records them
as a watch list so buyers are not told we lag an unreleased cut.

Measured on the same Ollama corpus: [benchmark vs LiteLLM](benchmark-vs-litellm.md). Short matrix: [compare](compare.md).
