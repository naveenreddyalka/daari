# What is daari?

**daari** (Telugu: path, way) is an open-source **local-first LLM execution router**. One process on your machine owns policy, cache, tools, and model selection. Frontier APIs are a last resort.

## Router, not proxy

| Typical proxy (e.g. LiteLLM) | daari |
|-----------------------------|-------|
| Fan-out to many cloud providers | Prefer **on-device** tiers first |
| Keys and rate limits for cloud | Cache + tools + local models cut spend |
| Observability of provider calls | **Measured cache trust** + savings ledger |

daari is for developers and product teams who want **local execution** with a controlled escalation path—not a marketplace of 100+ remote models.

## What it owns

1. **Gateways** — OpenAI, Anthropic Messages, Responses API, Ollama facade, MCP
2. **Routing** — Ordered tiers from exact cache through local models to frontier
3. **Trust** — False-hit monitoring, optional product **boundaries**, guardrails
4. **Clients** — One-click setup for Cursor, Claude Code, JetBrains, VS Code
5. **Learning** — Opt-in feedback and fine-tune loop on your machine

## When to use it

- IDE agents burning frontier tokens on repeatable work
- B2C/SaaS chat that must stay inside a product domain ([boundaries](boundaries-and-guardrails.md))
- Teams that want org shared cache / fleet bootstrap without a hosted SaaS

## Next

→ [Routing tiers](routing-tiers.md) · [Quickstart](../get-started/quickstart.md)
