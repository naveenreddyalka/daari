# ADR-0010: Browser bridge and Google search for Lt-fetch

Date: 2026-06-15  
Status: **accepted**

## Context

For L2-live queries (weather, facts, news), users may prefer **Google search** or **authenticated browser access** over niche APIs like Open-Meteo. Reasons:

- One familiar source (Google) for many question types
- User already logged into Google in browser
- No separate API key per provider (weather, stocks, news)
- Enterprise users may need SSO/authenticated intranet pages

ADR-0009 deferred browser to C2+. This ADR defines **how** Google + browser auth fit daari.

## Decision

Support **three Lt-fetch backends** for live facts, in priority order (configurable):

```
1. Structured API     (Open-Meteo, etc.)     — fast, no auth
2. Google Search API  (official JSON API)    — broad, needs API key
3. Browser bridge     (extension + user session) — Google auth, any logged-in site
```

User picks default in `~/.daari/sources.yaml`. All paths avoid L3/L6 when successful.

---

## Option A — Google Custom Search JSON API (official)

**Not** scraping google.com. Google's supported programmatic search:

| Item | Detail |
|------|--------|
| Product | [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview) |
| Auth | API key + Programmable Search Engine ID |
| Cost | Free tier (~100 queries/day), then paid |
| Phase | **C1** |
| Module | `daari/tools/search_google_api.py` |

```yaml
# sources.yaml
search:
  provider: google_cse
  api_key: ${GOOGLE_CSE_API_KEY}
  cx: ${GOOGLE_CSE_ID}   # search engine id
```

**Weather via Google:** query `"weather San Francisco today"` → parse snippets from results → template format locally (no LLM).

**Pros:** Legal, stable, no browser. **Cons:** API key, daily limits, snippet quality varies.

---

## Option B — Browser extension + daari bridge (user Google auth)

User stays logged into Google (and other sites) in **their** browser. A **daari browser extension** acts as Lt-fetch backend using the **existing session** — no Google password stored in daari.

### Architecture

```
daari daemon (Python)
      │  localhost WebSocket / native messaging
      ▼
daari browser extension (Chrome/Firefox)
      │  uses user's logged-in tabs / opens background search
      ▼
Google Search (or any site user is authed to)
      │  extract title, snippet, answer box
      ▼
extension → daemon → CCS → reply to Cursor
```

### Components

| Component | Language | Role |
|-----------|----------|------|
| `daari-bridge` service | Python (in daemon) | WebSocket server on localhost |
| Browser extension | **TypeScript** | Search, extract, return structured JSON |
| Auth | **Browser-native** | User logs into Google in Chrome — daari never sees password |

### Extension capabilities (phased)

| Phase | Capability |
|-------|------------|
| C2.0 | Google web search → return top snippets |
| C2.1 | Google answer boxes (weather widget, knowledge panel) |
| C2.2 | User-approved domains (Confluence, internal wiki) via logged-in session |
| C3 | Optional Playwright fallback for headless (no extension) — power users |

### User flow

1. `daari setup browser-extension` — install extension, pair with daemon (one-time token)
2. User logs into Google normally in browser
3. "How's the weather?" → L2-live → Lt-fetch **browser** → extension runs search → extracts "72°F" from results page
4. CCS caches 30 min

### Security

| Rule | Detail |
|------|--------|
| Pairing | One-time code; extension only talks to `127.0.0.1` |
| Scope | Extension only acts on daari-initiated searches (not general browsing spy) |
| Confirm | Optional: confirm before search on sensitive profiles |
| OSS | Extension source published; users audit permissions |
| No password storage | Session cookies stay in browser |

---

## Option C — Playwright with user Chrome profile (no extension)

Alternative to extension: daari launches Playwright attached to user's Chrome profile (opt-in).

| Pros | Cons |
|------|------|
| No extension install | Heavier; macOS permissions |
| Reuses Google login | Fragile on Chrome updates |
| Good for automation users | Google may flag automated search |

**Phase C2+**, **opt-in only**, documented as advanced. Extension is the **recommended** browser path.

---

## Recommended rollout

| Phase | Lt-fetch backend | Weather example |
|-------|------------------|-----------------|
| **C1** | Open-Meteo API + optional Google CSE API | API first; Google CSE fallback |
| **C2** | **Browser extension** + Google CSE | Extension search "weather today" → parse answer box |
| **C2+** | Playwright profile (opt-in) | Same, for users who refuse extension |

**Open-Meteo stays** as fast zero-auth fallback when user doesn't want Google/network search.

---

## Provider priority (config)

```yaml
# ~/.daari/sources.yaml
live_fetch:
  enabled: true
  priority:
    - open_meteo          # weather-specific, free
    - google_cse          # broad search, API key
    - browser_extension   # user's Google session
  browser:
    extension_paired: true
    require_answer_box: true   # prefer structured weather widget
  fallback: L3             # only if all fetch backends fail
```

---

## Module placement

```
daari/tools/
  weather.py           # Open-Meteo
  search_google_api.py # Google CSE (C1)
  browser_bridge.py    # WebSocket to extension (C2)

browser-extension/     # separate package, TypeScript
  src/background.ts
  src/content-extract.ts
  manifest.json
```

Browser extension is **TypeScript** (standard for Chrome/Firefox) — Python daemon stays the brain ([ADR-0005](0005-python-tech-stack.md)).

---

## Consequences

**Positive**
- Google search with user's own auth — no LLM hallucination
- One extension covers weather, news, stocks, arbitrary facts
- Authenticated enterprise pages possible (C2.2)

**Negative**
- Extension is significant build + Chrome Web Store or sideload
- Google ToS: programmatic search must use CSE API; extension uses **user-initiated browser search** (different legal shape — user's browser, user's session)
- Not offline; network required
- Parsing search results is brittle vs structured APIs

## Related

- [ADR-0009](0009-live-factual-fetch-l2-live.md) — L2-live + Lt-fetch
- PRD user stories #65–67
