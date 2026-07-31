# Common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Connection refused | Daemon down | `daari serve` / Compose |
| 401 Unauthorized | API key required | Send Bearer / generate via tunnel setup |
| `/ready` not ready | Ollama missing model | `ollama pull …` or wait for Compose pull |
| Cursor private network error | Localhost BYOK | Use tunnel HTTPS URL |
| Empty Cursor reply | Tool/content quirks | Check request log; restart serve from venv |
| Always escalates to L6 | Confidence / missing models | Pull L4; tune thresholds; set tier cap |
| `tier=boundary` unexpected | Boundaries deny | Adjust topics or `mode: warn` |
| Redis/Postgres errors | Optional backend | Install extras; check URLs |

For security issues see [Security](../resources/security.md) — do not file public issues for vulns.
