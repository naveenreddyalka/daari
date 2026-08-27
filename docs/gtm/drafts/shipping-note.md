# Shipping note — daari 1.3.0

Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), distributed rate limits, health-checked local backend pool, real token accounting, and a move to PolyForm Noncommercial 1.0.0.

- **Relicensed from Apache 2.0 to [PolyForm Noncommercial 1.0.0](../LICENSE)** (#202): free for personal, educational, research, and other noncommercial use; commercial use requires a separate license (contact naveenreddy.alka@gmail.com). Releases through v1.2.0 remain available under Apache 2.0. CONTRIBUTING.md now includes a contributor relicense grant.
- **Responses API completed for agents** (#196): background mode, `previous_response_id` chaining, response store, streaming events
- **Real MCP JSON-RPC server at `POST /mcp`** (#195): tools/list, tools/call over the gateway
- **`POST /v1/embeddings`** on the OpenAI surface (#193)
- **Vision requests keep image parts** (#192); OpenAI sampling parameters honored instead of dropped (#187)
- **Native Anthropic `/v1/messages` L6 egress** (#194): no more lossy OpenAI-format round-trip for Claude

Docs: https://naveenreddyalka.github.io/daari/
Repo: https://github.com/naveenreddyalka/daari

Source-available under PolyForm Noncommercial — personal/research free; commercial use needs a license.

This file is a draft. A human publishes it. Do not auto-post to HN, Reddit, or X.

## X draft

daari 1.3.0: Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), dis https://naveenreddyalka.github.io/daari/ (Source-available under PolyForm Noncommercial)

## LinkedIn draft

Shipped daari 1.3.0. Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), distributed rate limits, health-checked local backend pool, real token accounting, and a move to PolyForm Noncommercial 1.0.0. Install: pip install daari. https://naveenreddyalka.github.io/daari/ Source-available under PolyForm Noncommercial — personal/research free; commercial use needs a license.
