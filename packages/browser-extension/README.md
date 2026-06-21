# daari browser extension (MVP)

Minimal MV3 extension that sends prompts to local daari.

## What it does

- Popup UI with prompt textarea and send button.
- Sends request to configurable API base URL (default `http://127.0.0.1:11435`).
- Renders assistant response and `daari_meta` tier payload.
- Persists latest draft prompt in `chrome.storage.local`.
- Includes an options page to update API base URL.

## Files

- `manifest.json` — MV3 manifest + localhost permissions.
- `popup.html` — popup layout.
- `popup.css` — popup styling.
- `popup.js` — request/response logic.
- `options.html` — extension options page.
- `options.js` — API base URL persistence.

## Load in browser

1. Open browser extension page (`chrome://extensions` or Edge equivalent).
2. Enable Developer Mode.
3. Choose **Load unpacked** and select `packages/browser-extension`.
4. Start daari (`daari serve`) and open extension popup.
5. Optional: click **Options** in popup and set a different daemon base URL.
