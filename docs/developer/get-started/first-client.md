# First client

**Outcome:** Point Cursor or an OpenAI-compatible SDK at daari.

## OpenAI SDK (any language)

```bash
export OPENAI_BASE_URL=http://127.0.0.1:11435/v1
export OPENAI_API_KEY=daari   # or your server.api_key / virtual key
```

```python
from openai import OpenAI
client = OpenAI()  # uses env
print(client.chat.completions.create(
    model="daari",
    messages=[{"role": "user", "content": "Say hi"}],
).choices[0].message.content)
```

Or: `daari setup openai-compat`.

## Cursor (requires tunnel)

Cursor cloud cannot call localhost. Use:

```bash
scripts/tunnel.sh --setup-cursor
```

Full guide: [Cursor client guide](../guides/clients/cursor.md) · Tutorial: [Cursor BYOK tunnel](../tutorials/cursor-byok-tunnel.md).

## Claude Code / JetBrains / VS Code

```bash
daari setup claude-code
daari setup intellij
daari setup vscode
```

See [Guides → Clients](../guides/clients/cursor.md).

## Verify

Send a prompt from the client, then:

```bash
daari stats
daari report
```

## Next

→ [What is daari?](../concepts/what-is-daari.md) · [Project profiles](../guides/configuration/project-profiles.md)
