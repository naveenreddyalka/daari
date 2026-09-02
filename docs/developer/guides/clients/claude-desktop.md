# Claude Desktop

**Outcome:** Claude Desktop chats route through daari's Anthropic gateway instead
of the Anthropic cloud — local tiers first, frontier only when needed, with
cache, budgets and traces that pointing it at raw Ollama cannot give you.

Claude Desktop's *third-party inference* mode accepts any Anthropic-shaped
gateway (the same mode Ollama 0.33 uses). daari speaks that protocol at
`/v1/messages`, so the recipe only has to hand the app a configuration file.

## Prerequisites

- `daari serve` on `http://127.0.0.1:11435`
- Claude Desktop installed (macOS, Windows or Linux)

## Steps

```bash
daari setup claude-desktop --dry-run
daari setup claude-desktop
daari serve   # if not already running
```

Then **fully quit and reopen Claude Desktop** (configuration is read once at
launch). If daari is not active, open **Developer → Configure Third-Party
Inference… → Import configuration** and pick the file the recipe wrote.

The recipe writes `daari.json` into the app's saved-configuration library
(backup first when a file already exists):

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Claude-3p/configLibrary/daari.json` |
| Windows | `%LOCALAPPDATA%\Claude-3p\configLibrary\daari.json` |
| Linux | `~/.config/Claude-3p/configLibrary/daari.json` |

```json
{
  "inferenceProvider": "gateway",
  "inferenceGatewayBaseUrl": "http://127.0.0.1:11435",
  "inferenceGatewayApiKey": "daari-local",
  "inferenceGatewayAuthScheme": "x-api-key",
  "inferenceModels": [{ "name": "daari", "labelOverride": "daari (local-first)" }]
}
```

The base URL has no `/v1` suffix — the app appends `/v1/messages` itself, the
same as Claude Code. When `server.api_key` is set, the recipe writes that key
instead of `daari-local`. No tunnel required (localhost is fine).

`daari setup all` includes this recipe and skips cleanly when Claude Desktop is
not installed.

## Manual fallback

If you prefer not to let daari write into the app directory, or the app rejects
the library file:

1. Save the JSON above anywhere (e.g. `~/daari-claude-desktop.json`).
2. In Claude Desktop open **Developer → Configure Third-Party Inference…**.
3. Set **Inference provider** to *Gateway*, then **Import configuration** and
   choose the file — or type the values by hand: Gateway base URL
   `http://127.0.0.1:11435`, Gateway API key `daari-local`, Credential kind
   *Static API key*, Gateway auth scheme *x-api-key*.
4. Quit and reopen the app.

Managed (MDM) deployments: the same keys go into the `.mobileconfig` /
registry policy / `/etc/claude-desktop/managed-settings.json`; a managed source
wins over the local library. See Anthropic's
[gateway provider reference](https://claude.com/docs/third-party/claude-desktop/providers/gateway)
for the full key list.

## Verify

Chat once, then `daari report`. Requests arrive on `/v1/messages`; the
`x-daari-tier` / `x-daari-cache` response headers show which tier served them.

## Troubleshoot

| Problem | Fix |
|---------|-----|
| App still uses Anthropic cloud | Fully quit (not just close the window) and reopen; check Developer → Configure Third-Party Inference… shows the daari configuration as applied |
| "no credential configured for provider gateway" | The API key field is empty — re-run `daari setup claude-desktop --force` |
| Model picker empty | daari's `/v1/models` must be reachable; the pinned `inferenceModels` entry shows `daari` regardless |
| MDM-managed machine ignores the file | A managed source wins; ask your admin to push the keys above |

## Undo

```bash
daari setup --undo claude-desktop
```

Restores the previous `daari.json` from backup, or removes the daari-written
file when there was none.

## Next

→ [MCP](mcp.md) — expose daari's tools to Claude Desktop as well  
→ [Project profiles](../configuration/project-profiles.md)
