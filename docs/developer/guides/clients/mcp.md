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

This is the *tools* path. To route Claude Desktop's chat itself through daari
(third-party gateway mode), see the [Claude Desktop guide](claude-desktop.md) —
`daari setup claude-desktop`.

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

## Tool guardrails (arguments and results)

Policy decides *which* tools a caller may invoke; guardrails inspect *what
flows through them*. `integrations.mcp_guardrails` has the same shape as the
top-level [`guardrails`](../../reference/config.md) block and is off by
default. When enabled, `input_rules` (plus `max_prompt_chars` and the built-in
prompt-injection heuristics) run over the flattened `tools/call` arguments
before execution, and `output_rules` run over the result after — the same
`block` / `warn` / `redact` semantics chat requests get, applied on the machine
where the tools run.

```yaml
integrations:
  mcp_guardrails:
    enabled: true
    block_message: "Tool result withheld by daari guardrail."
    input_rules:
      - { name: no_rm_rf, pattern: 'rm\s+-rf', action: block }
    output_rules:
      - { name: secrets, kind: secret, action: redact }
      - { name: pii, kind: pii, action: redact }
```

What the caller sees:

- An input trip on `POST /mcp` is JSON-RPC error `-32003`
  (`Tool call blocked by guardrail <rule>: <tool>`, `data` carries `tool`,
  `rule` and `direction: input`). On `/v1/mcp/query` it is HTTP `403` with
  `MCP_ERR_GUARDRAIL_BLOCKED` and the same fields under `details`.
- An output `redact` rewrites every text item of the result in place
  (`<aws_key>`, `<email>`, `<redacted>`, …). An output `block` replaces the
  whole result with `block_message` and sets `isError: true` (legacy route:
  `ok: false`). Task results (`tasks/get`) are checked the same way before
  they are stored.
- The egress client applies the same rules: outbound arguments are checked
  before the request leaves the machine (a block returns a
  `guardrail_blocked` warning instead of calling the server), and inbound
  results are scrubbed before the model sees them.

Every trip, input or output, appends an `mcp.guardrail` row to the audit log
next to the `mcp.tools/call` decision rows: key id / team, tool, rule name,
direction, action, transport. The payload itself is never written.

## Tasks (long-running tools/call)

When the negotiated protocol is `2026-07-28` or newer, `initialize` advertises
the `io.modelcontextprotocol/tasks` capability. Clients opt in per call:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "route",
    "arguments": {"input": "run the suite"},
    "_meta": {"io.modelcontextprotocol/tasks": true}
  }
}
```

Eligible tools (default: `route`, or any tool when
`integrations.mcp_tasks.threshold_ms > 0`) return a `taskId` immediately;
poll with `tasks/get`, acknowledge state with `tasks/update`, and stop work
with `tasks/cancel`. Calls without the `_meta` opt-in keep today's blocking
behavior. Governance (#277) still audits the call before a task is created.

```yaml
integrations:
  mcp_tasks:
    enabled: true
    long_running_tools: [route]
    threshold_ms: 0
    path: ~/.daari/mcp-tasks
```

## Deprecated alias

`POST /v1/mcp/query` remains for older callers. Responses include
`Deprecation: true` and `Link: </mcp>; rel="successor-version"`.

## Next

→ [Clients and gateways](../../concepts/clients-and-gateways.md) · [Auth and keys](../configuration/auth-and-keys.md)
