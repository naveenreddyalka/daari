# ADR-0009: Live factual queries (L2-live) and external fetch (Lt-fetch)

Date: 2026-06-15  
Status: **accepted**

## Context

Users may ask **live factual questions** that do not need an LLM:

- "How is the weather today?"
- "What's the current price of AAPL?"
- "Who won the game last night?"

Sending these to L3/L6 wastes tokens and may hallucinate. Better: **fetch from a real source**, format locally, cache briefly — same philosophy as Lt for dev commands.

This is **not L2-dev** (coding commands). It is a parallel pattern: **L2-live**.

## Decision

Add **L2-live** rules + **Lt-fetch** backends + **CCS** (short TTL):

```
L2-live (detect)  →  Lt-fetch (call source)  →  CCS (cache)  →  reply
   rules                 API / search              30–60 min TTL    no model
```

### 1. L2-live — factual / live-data rules (extends L2)

| Pattern class | Examples | Lt-fetch backend |
|---------------|----------|------------------|
| **weather** | "weather today", "temperature in SF" | Weather API (Open-Meteo, etc.) |
| **web_search** | "search for X", "latest news on Y" | Search API or fetch (configurable) |
| **finance** | "stock price AAPL" | Finance API (if configured) |
| **general_fact** | low-confidence → escalate to L3 | — |

Rules in `~/.daari/sources.yaml` — user enables providers and API keys.

### 2. Lt-fetch — external data backends (extends Lt)

**Lt-fetch** is part of the **Tool executor** module — not a new tier letter:

```
daari/tools/
  shell.py      # L2-dev → local commands
  fetch.py      # L2-live → HTTP APIs
  search.py     # optional web search provider
```

| Source type | MVP approach | Browser? |
|-------------|--------------|----------|
| Weather | **Structured API** (Open-Meteo — free, no key) | No |
| Web search | Search API (Brave, SerpAPI, etc.) if user configures key | No |
| Generic URL | HTTP GET + extract (readability) | No |
| Browser automation | Playwright/Puppeteer | **Phase C+ only** — heavy, opt-in |

**Default:** APIs and HTTP fetch — **not** opening Google in a browser for MVP.

### 3. CCS for live data

Same Command Context Store as ADR-0008, different TTL:

| Query type | CCS TTL |
|------------|---------|
| Weather | 30–60 min |
| Stock price | 1–5 min |
| News search | 5–15 min |

Follow-up "what about tomorrow?" may need new fetch or L3 — router decides.

### Routing placement

```
L0 → CCS → L1 → L2-dev → L2-live → L2 generic → Lt (shell | fetch) → L3 … L6
```

**Weather example:**

```
"How's the weather today?"
  → L2-live match (weather)
  → CCS miss (or stale)
  → Lt-fetch → Open-Meteo API
  → format answer locally (template, no LLM)
  → CCS write (TTL 30m)
  → return "72°F, sunny in San Francisco"
```

**No L3/L6 invoked.**

### Privacy & cost

| Concern | Policy |
|---------|--------|
| Network egress | Lt-fetch **does** call external APIs — user configures in `sources.yaml` |
| vs L6 | Still cheaper and more accurate than LLM guessing |
| API keys | User-owned, local config |
| Disable | `sources.enabled: false` → weather queries fall through to L3 or error clearly |
| Telemetry | Off by default (ADR-0006) |

## Phase

| Component | Phase |
|-----------|-------|
| L2-live weather + Open-Meteo | **B.1** or **C1** |
| Web search provider | **C1** (requires API key) |
| Browser automation | **C2+** (opt-in, not default) |
| `.daari/sources.yaml` | **C1** |

**Not in Phase A** tracer bullet.

## Module placement

| Piece | Module |
|-------|--------|
| L2-live patterns | `daari/rules/live_facts.py` |
| Lt-fetch executors | `daari/tools/fetch.py`, `daari/tools/weather.py` |
| CCS (live TTL) | `daari/cache/command_context.py` (shared with ADR-0008) |
| Provider config | `~/.daari/sources.yaml` |

## Consequences

**Positive**
- Extends "no AI when unnecessary" beyond dev commands
- Accurate live data vs hallucination
- CCS avoids hammering APIs

**Negative**
- External dependency + network required for live queries
- Not "fully offline" for weather — honest limitation
- Browser path is complex; defer to APIs first

## Related

- [ADR-0008](0008-developer-command-rules-and-context-cache.md) — L2-dev + CCS pattern (same shape)
- PRD user stories #62–64
