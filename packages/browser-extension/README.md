# daari browser extension

MV3 extension that bridges prompts to local daari — popup UI plus content-script
interception of in-page chat widgets (issue #171).

## What it does

- **Popup** — textarea → `POST /v1/chat/completions` on the local daemon (default `http://127.0.0.1:11435`); shows response, `daari_meta`, and session tier / estimated savings.
- **Content script** — for matched site profiles, intercepts chat submit, routes the prompt to daari with `X-Daari-Boundary-Profile`, and injects the local answer. If the daemon is down or the boundary refuses (`tier=boundary`), the page's own submit handler runs unchanged.
- **Options** — configurable API base URL.
- **Draft persistence** — latest popup prompt in `chrome.storage.local`.

## Site profiles

Shipped profiles live in [`lib/profiles.js`](lib/profiles.js):

| Id | Demo host | Boundary profile |
|----|-----------|------------------|
| `fintech-assist` | `127.0.0.1:8765` / `localhost:8765` | `fintech-assist` |
| `docs-support` | `127.0.0.1:8766` / `localhost:8766` | `docs-support` |

Demo pages: [`demo/fintech.html`](demo/fintech.html), [`demo/docs-support.html`](demo/docs-support.html).

```bash
# terminal A
python3 -m http.server 8765 --directory packages/browser-extension/demo
# open http://127.0.0.1:8765/fintech.html

# terminal B
python3 -m http.server 8766 --directory packages/browser-extension/demo
# open http://127.0.0.1:8766/docs-support.html
```

Merge [`examples/boundaries/extension-site-profiles.yaml`](../../examples/boundaries/extension-site-profiles.yaml) into `~/.daari/config.yaml` so named boundary overlays exist for the header.

### Add another site

1. Append an entry to `PROFILES` in `lib/profiles.js` (`hosts`, `selectors`, `boundaryProfile`).
2. Add matching `host_permissions` + `content_scripts.matches` in `manifest.json` (keep them narrow).
3. Add the same id under `boundaries.profiles` in daemon config.
4. Reload the unpacked extension.

## Host permissions (store listing)

Requested only for:

- `http://127.0.0.1:11435/*` and `http://localhost:11435/*` — talk to the local daari daemon.
- `http://127.0.0.1:8765/*`, `http://localhost:8765/*`, `http://127.0.0.1:8766/*`, `http://localhost:8766/*` — local demo chat widgets used by the shipped site profiles.

No remote SaaS origins are requested by default. Adding a production site requires an explicit manifest edit (see above).

## Privacy

| Reads | Leaves the browser | Never leaves |
|-------|--------------------|--------------|
| Text typed into matched chat inputs and the popup textarea | Prompt text + optional boundary profile id to the configured daari base URL (default loopback only) | Cookies, passwords, or unrelated page DOM outside the configured selectors |
| Session counters (tier, estimated savings) in `chrome.storage.local` | Stay on-device unless you point the API base at a non-local URL | Analytics, accounts, or third-party telemetry |

The extension does not scrape the full page. Fallback to the site's own backend uses the page's existing network path; daari never sees that traffic.

## Files

- `manifest.json` — MV3, narrow host permissions, content script matches, module service worker.
- `background.js` — daemon proxy + session stats.
- `content.js` — in-page intercept / fallback.
- `lib/` — profiles, daemon client, session, intercept (jsdom-tested).
- `popup.*` / `options.*` — manual bridge UI.
- `demo/` — two local chat widgets for the shipped profiles.

## Tests

```bash
cd packages/browser-extension
npm install
npm test
```

Covers popup send/error UX, options save/load, profile matching, interception, daemon-down fallback, and boundary refusal fallback. Runs in CI as the `extension` job.

## Load in browser

1. Open `chrome://extensions` (or Edge equivalent), enable Developer Mode.
2. **Load unpacked** → select `packages/browser-extension`.
3. Start daari (`daari serve`) with the extension boundary example config.
4. Open a demo page (ports 8765 / 8766) or the popup.
