# daari web-ui

Minimal static dashboard for local daari runtime metrics.

## Start

```bash
daari web-ui serve
```

Default URL: `http://127.0.0.1:11437`  
Default API source: `http://127.0.0.1:11435/v1`

Use custom API base:

```bash
daari web-ui serve --api-base-url http://127.0.0.1:11535
```

When the daemon has `server.api_key` (or virtual keys / SSO JWT), paste the Bearer token into the **API key / Bearer** field in the toolbar — it is stored in `localStorage` and sent on all dashboard and config-editor requests.

## What it shows

- `GET /v1/daari/stats` summary (`total_requests`, `errors`)
- Tier breakdown table (`count`, `p50_ms`, `p95_ms`)
- Tier count bar chart for quick visual distribution
- Auto-refresh controls (on/off + refresh interval)
- Optional org-learning summary + metrics from `GET /v1/org-learning/profile` when reachable
- Export current stats snapshot as JSON
- Dark/light theme toggle (persisted locally)

## Files

- `index.html` layout shell
- `app.js` stats fetching and rendering logic
- `styles.css` lightweight styling
- `ARCHITECTURE.md` design notes

## Tests

DOM-level tests run with Node's test runner + jsdom:

```bash
cd packages/web-ui
npm install
npm test
```
