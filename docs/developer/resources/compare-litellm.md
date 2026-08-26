# daari vs LiteLLM

LiteLLM is a **provider gateway**: one OpenAI-shaped API in front of 100+ cloud models. daari is a **local cost optimizer**: cache, tools, and Ollama/MLX first, frontier last.

| | LiteLLM | daari |
|--|---------|-------|
| Job | Talk to many remote providers | Keep repeat agent work on your machine |
| Default path | Cloud / configured backends | L0/L1 cache → tools → local → L6 |
| Cache | Optional Redis/Qdrant | Built-in exact + semantic, measured false-hit rate |
| IDE setup | DIY | `daari setup cursor` / Claude Code / JetBrains / VS Code |
| License | MIT-class (OSI) | PolyForm Noncommercial (source-available; commercial use needs a license) |
| Stars / mindshare | Category default | New |

**Pick LiteLLM** if you need 100 providers, virtual keys across a team, and an MIT license.

**Pick daari** if Cursor or Claude Code is burning frontier tokens on work a cache or a 3B local model can do, and you want that path to be the default.

They can stack: daari for local $0 tiers, LiteLLM (or OpenRouter) as one L6 slot.

Measured on the same Ollama corpus: [benchmark vs LiteLLM](benchmark-vs-litellm.md). Short matrix: [compare](compare.md).
