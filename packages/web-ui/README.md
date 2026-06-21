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

## What it shows

- `GET /v1/daari/stats` summary (`total_requests`, `errors`)
- Tier breakdown table (`count`, `p50_ms`, `p95_ms`)
- Optional org-learning metrics from `GET /v1/org-learning/profile` when reachable

## Files

- `index.html` layout shell
- `app.js` stats fetching and rendering logic
- `styles.css` lightweight styling
- `ARCHITECTURE.md` design notes
