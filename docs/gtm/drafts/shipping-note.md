# Shipping note — daari 1.3.0

Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), distributed rate limits, health-checked local backend pool, real token accounting, and a move to PolyForm Noncommercial 1.0.0.

- **Relicensed from Apache 2.0 to PolyForm Noncommercial 1.0.0** (#202). Later reversed on `main` by #227.
- **Responses API completed for agents** (#196): background mode, `previous_response_id` chaining, response store, streaming events
- **Real MCP JSON-RPC server at `POST /mcp`** (#195): tools/list, tools/call over the gateway
- **`POST /v1/embeddings`** on the OpenAI surface (#193)
- **Vision requests keep image parts** (#192); OpenAI sampling parameters honored instead of dropped (#187)
- **Native Anthropic `/v1/messages` L6 egress** (#194): no more lossy OpenAI-format round-trip for Claude

Docs: https://naveenreddyalka.github.io/daari/
Repo: https://github.com/naveenreddyalka/daari

Apache 2.0 — OSI open source.

This file is a draft. A human publishes it. Do not auto-post to HN, Reddit, or X.

## X draft

daari 1.3.0: Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), dis https://naveenreddyalka.github.io/daari/ (Apache 2.0)

## LinkedIn draft

Shipped daari 1.3.0. Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), distributed rate limits, health-checked local backend pool, real token accounting, and a move to PolyForm Noncommercial 1.0.0. Install: pip install daari. https://naveenreddyalka.github.io/daari/ Apache 2.0 — OSI open source.
