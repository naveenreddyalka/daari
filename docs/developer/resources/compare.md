# Compare (short)

| | daari | OpenRouter | LiteLLM-style proxy |
|--|-------|------------|---------------------|
| Primary goal | Local $0 + trusted cache | Hosted 400-model marketplace | Many cloud providers, self-host |
| Default inference | On-device | Remote, billed | Remote / Ollama as one backend |
| Agent prompt reread | Exact L0 on identical `tools` + history (G1); L1 still off | Provider prompt-cache, cheaper not free | Optional Redis/Qdrant |
| Same-model provider pick | Honors OpenRouter `provider` on L6 (G2); ZDR fail-closed | Price / latency / throughput + ZDR | Fallback between deployments |
| IDE one-click | Cursor/Claude/JB/VS Code | API + playground | DIY |

OpenRouter (Stripe, Aug 2026) is not a clone target. Full gap + 90-day plan:
[ROADMAP-v3](../../prd/ROADMAP-v3.md).

Buyer pages (when to pick which, licenses named):

- [daari vs LiteLLM](compare-litellm.md)
- [daari vs Ollama](compare-ollama.md)
- [daari vs OpenRouter](compare-openrouter.md)

Measured head-to-head on this machine:
[vs LiteLLM](benchmark-vs-litellm.md) · [load RPS](benchmark-load.md).

Deep notes: `docs/discovery/04-competitive-landscape.md`.

