# Sources Integration — Open APIs + Google

> **Status:** Draft  
> **Related:** [ADR-0009](../adr/0009-live-factual-fetch-l2-live.md) · [ADR-0010](../adr/0010-browser-bridge-google-search.md) · [PRD](PRD.md)

---

## Requirement

daari **must integrate both**:

1. **Open / structured APIs** — weather, finance, etc. (fast, free, accurate)
2. **Google** — Custom Search API + browser extension with user auth (broad coverage)

This is **not either/or**. Users configure priority; daari ships providers for **both families**.

---

## Architecture

```
L2-live (detect: weather, fact, search)
        │
        ▼
   Lt-fetch router (sources.yaml priority)
        │
   ┌────┴────────────────────────────┐
   ▼                                 ▼
Open API providers              Google providers
(fast, structured)              (broad, search)
   │                                 │
   ├─ Open-Meteo (weather)           ├─ Google Custom Search JSON API (C1)
   ├─ wttr.in (weather fallback)     ├─ Browser extension + user session (C2)
   ├─ Exchange rate APIs (future)    └─ (optional) Google Weather via search snippets
   └─ … pluggable registry
        │
        ▼
      CCS (cache by query type + TTL)
        │
        ▼
   Formatted reply (template — no LLM)
```

---

## Open API providers (required)

| Provider | Use case | Auth | Phase | Module |
|----------|----------|------|-------|--------|
| **Open-Meteo** | Weather forecast | None | **C1** | `daari/tools/weather_open_meteo.py` |
| **wttr.in** | Weather fallback (terminal-friendly) | None | **C1** | `daari/tools/weather_wttr.py` |
| **HTTP generic** | Any OpenAPI/REST URL in config | Optional key | **C1** | `daari/tools/fetch.py` |
| Exchange / finance APIs | Stock prices | API key | **C2+** | pluggable |

### Example — weather without Google

```
"How's the weather in San Francisco?"
  → L2-live (weather)
  → Lt-fetch → Open-Meteo API
  → "72°F, partly cloudy, humidity 65%"
```

**Why keep open APIs when we have Google?**
- Faster (direct JSON vs search parse)
- No API key / no Google account
- More reliable structured data
- Works offline-ish (cached in CCS)

---

## Google providers (required)

| Provider | Use case | Auth | Phase | Module |
|----------|----------|------|-------|--------|
| **Google Custom Search JSON API** | General search, weather snippets, news | API key + CSE id | **C1** | `daari/tools/search_google_api.py` |
| **Browser extension** | Search with user's Google login | Browser session | **C2** | `browser-extension/` (TS) + `browser_bridge.py` |

### Example — weather via Google

```
"How's the weather today?"
  → L2-live (weather)
  → Open-Meteo fails or disabled
  → Lt-fetch → Google CSE "weather San Francisco today"
  → parse answer box / top snippet
  → "72°F, sunny"
```

### Example — browser extension

```
User paired extension, logged into Google in Chrome
  → Lt-fetch → browser_bridge → extension opens search
  → extracts knowledge panel / weather widget
  → CCS cache 30 min
```

**Why Google when we have open APIs?**
- One integration for weather + news + stocks + arbitrary facts
- User's authenticated session (personalized, enterprise)
- Fallback when no open API exists for the question type

---

## Config — `~/.daari/sources.yaml`

```yaml
live_fetch:
  enabled: true

  # Try in order; first success wins
  priority:
    - open_api          # structured providers below
    - google_cse        # Google Custom Search API
    - browser_extension # paired Chrome/Firefox extension

open_api:
  weather:
    primary: open_meteo
    fallback: wttr
    location: auto       # from IP, config, or user message

google:
  cse:
    enabled: true
    api_key: ${GOOGLE_CSE_API_KEY}
    cx: ${GOOGLE_CSE_ID}
  browser_extension:
    enabled: false       # enable after C2 pairing
    paired: false
    host: "127.0.0.1:11436"

cache:                   # CCS TTLs
  weather_seconds: 1800
  search_seconds: 900
  stock_seconds: 300

fallback: L3              # model only if all sources fail
```

Per-project overrides: `.daari/sources.yaml` in repo (optional).

---

## Provider registry (implementation)

```python
# Conceptual — daari/tools/sources/registry.py
PROVIDERS = {
    "open_meteo": OpenMeteoProvider(),
    "wttr": WttrProvider(),
    "google_cse": GoogleCSEProvider(),
    "browser_extension": BrowserExtensionProvider(),
}
```

New open APIs or Google surfaces = **register provider**, no router rewrite.

---

## Phase delivery

| Phase | Open APIs | Google |
|-------|-----------|--------|
| **A** | — | — |
| **B** | — | — |
| **C1** | Open-Meteo, wttr, generic HTTP | Google Custom Search API |
| **C2** | + finance APIs (optional) | Browser extension + user Google auth |
| **C2+** | Community plugins | Playwright profile (opt-in) |

---

## User stories (PRD)

See PRD #62–67 — both families explicitly required.

---

## Security summary

| Source | Leaves machine? | Credentials |
|--------|-----------------|-------------|
| Open-Meteo | Yes (HTTP to open-meteo.com) | None |
| Google CSE | Yes (Google API) | User API key in config |
| Browser extension | Yes (user's browser) | Session in browser only |

All opt-out via `live_fetch.enabled: false` or per-provider disable.
