# Compare (short)

| | daari | LiteLLM-style proxy | Portkey-style gateway |
|--|-------|---------------------|------------------------|
| Primary goal | Local cost + trust | Many cloud providers | Guardrails + observability SaaS |
| Default inference | On-device | Remote | Remote / hybrid |
| Cache trust metrics | First-class | Rare | Varies |
| IDE one-click | Cursor/Claude/JB/VS Code | DIY | DIY |

Measured head-to-head on the same machine and corpus:
[daari vs LiteLLM](benchmark-vs-litellm.md) (`python scripts/bench_vs_litellm.py --spawn`).

Deep competitive notes (internal): `docs/discovery/04-competitive-landscape.md`.
