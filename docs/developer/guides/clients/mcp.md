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

## Tool governance

Any authenticated caller can reach every tool unless you say otherwise. Policies
are glob-style `allow` / `deny` lists on tool names; deny always wins, and an
empty `allow` means "everything not denied". Three layers stack, narrowest last:

1. `integrations.mcp_policy` — global default (also governs the master key and
   open single-user installs).
2. `integrations.mcp_team_policies.<team>` — per team name, applied to keys
   created with `--team`.
3. The virtual key's `metadata.mcp` — per key.

Denies from every layer accumulate; the most specific `allow` list wins.

```yaml
integrations:
  mcp_policy:
    deny: ["mcp_prod_*"]
  mcp_team_policies:
    eng:
      allow: ["route", "stats", "mcp_*"]
```

Per-key policy is set at creation and stored in the key's metadata:

```bash
daari keys create ci-bot --team eng --mcp-allow route --mcp-allow 'mcp_*' --mcp-deny mcp_prod
```

What the caller sees:

- `tools/list` (JSON-RPC and `/v1/mcp/query`) only returns allowed tools.
- A denied `tools/call` on `POST /mcp` is JSON-RPC error `-32003`
  (`Tool denied by policy: <name>`, `data.tool` set).
- A denied call on the legacy `/v1/mcp/query` is HTTP `403` with
  `MCP_ERR_TOOL_DENIED`.

Every `tools/call` — allowed or denied — appends a row to the enterprise audit
log (`enterprise.audit_path`) with the key id or `master`, the team, the tool
name, the decision and the transport. Tool arguments are never written.

daari's MCP egress client sends the MCP 2026-07-28 routing headers
`Mcp-Method` and `Mcp-Name` on outbound requests, and the ingress honours the
same headers for policy when a client supplies them.

## Deprecated alias

`POST /v1/mcp/query` remains for older callers. Responses include
`Deprecation: true` and `Link: </mcp>; rel="successor-version"`.

## Next

→ [Clients and gateways](../../concepts/clients-and-gateways.md) · [Auth and keys](../configuration/auth-and-keys.md)
