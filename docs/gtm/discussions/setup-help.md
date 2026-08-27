# Cursor / Claude Code setup help

Use this thread when `daari setup cursor` or Claude Code BYOK is stuck. One question per reply; include the failing command and the last 20 lines of output (redact keys).

**Quick checks**

```bash
daari doctor
daari setup cursor --help
```

- Daemon: `GET http://127.0.0.1:11435/health` should be 200
- Cursor base URL should point at daari, not raw OpenAI
- Tunnel / API-key auth: see the Cursor guide

**Guides**

- Cursor: https://naveenreddyalka.github.io/daari/developer/guides/clients/cursor/
- Claude Code: https://naveenreddyalka.github.io/daari/developer/guides/clients/claude-code/
- Docs home: https://naveenreddyalka.github.io/daari/
- Repo: https://github.com/naveenreddyalka/daari

License: PolyForm Noncommercial (source-available). I am the author. Happy to debug a tunnel or key issue here — do not paste secrets.
