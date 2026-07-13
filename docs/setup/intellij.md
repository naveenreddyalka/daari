# IntelliJ setup (via the Ollama-compatible facade)

daari exposes a native Ollama-compatible API (`/api/tags`, `/api/chat`) at the
server root, so JetBrains AI Assistant connects to it exactly like a local
Ollama instance — full daari routing (cache, tiers, escalation) underneath.

## Steps (about 30 seconds)

1. Make sure the daemon is running: `daari serve` (or the launchd service).
2. In IntelliJ: **Settings → Tools → AI Assistant → Models**
   (on some versions: **Settings → Tools → AI Assistant → Third-party AI providers**).
3. Enable **Ollama** and set the URL to `http://127.0.0.1:11435`.
4. The model list populates automatically — pick **daari** for routed requests.

That's it. Requests show up in `daari report` attributed by client, and you can
send the `X-Daari-Client-Id: intellij` header from plugins that support custom
headers for cleaner attribution.

## Helper command

```bash
daari setup intellij --dry-run
daari setup intellij
```

This detects installed IntelliJ versions, writes a reference JSON
(`options/daari-openai-compat.json`) with the values above, and prints the
exact in-IDE steps. JetBrains does not expose a supported way to write the AI
Assistant provider config from outside the IDE, so the provider toggle remains
a one-time manual step.

## Other Ollama-speaking tools

The same facade works for anything that supports a custom Ollama URL
(Zed, Continue, Enchanted, etc.) — point them at `http://127.0.0.1:11435`.

## Undo

```bash
daari setup --undo intellij
```
