# MCP

**Outcome:** Cursor and Claude Desktop call daari as an MCP server (`route`, `stats`,
configured integrations).

daari speaks JSON-RPC 2.0 at `POST /mcp` over streamable HTTP. When `server.api_key`
is set, send the same Bearer / `x-api-key` the rest of the daemon expects.

## Cursor

`~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "daari": {
      "url": "http://127.0.0.1:11435/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_DAARI_KEY"
      }
    }
  }
}
```

Drop the `headers` object when the daemon has no API key.

## Claude Desktop

`claude_desktop_config.json` (Claude Desktop) or Claude Code MCP settings:

```json
{
  "mcpServers": {
    "daari": {
      "type": "http",
      "url": "http://127.0.0.1:11435/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_DAARI_KEY"
      }
    }
  }
}
```

## Tools

| Tool | What it does |
|------|----------------|
| `route` | Send `input` through daari's local-first pipeline |
| `stats` | Current tier metrics snapshot |
| `sourcegraph` / `ghe` / `gitlab` | Registered integration providers |
| `mcp_*` | Each `integrations.mcp_servers` entry |

## Deprecated alias

`POST /v1/mcp/query` remains for older callers. Responses include
`Deprecation: true` and `Link: </mcp>; rel="successor-version"`.

## Next

→ [Clients and gateways](../../concepts/clients-and-gateways.md) · [Auth and keys](../configuration/auth-and-keys.md)
