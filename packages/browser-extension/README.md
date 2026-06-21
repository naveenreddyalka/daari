# daari browser extension (MVP)

Minimal MV3 extension that sends prompts to local daari.

## What it does

- Popup UI with prompt textarea and send button.
- Sends request to `http://127.0.0.1:11435/v1/chat/completions`.
- Renders assistant response and `daari_meta` tier payload.
- Persists latest draft prompt in `chrome.storage.local`.

## Files

- `manifest.json` — MV3 manifest + localhost permissions.
- `popup.html` — popup layout.
- `popup.css` — popup styling.
- `popup.js` — request/response logic.

## Load in browser

1. Open browser extension page (`chrome://extensions` or Edge equivalent).
2. Enable Developer Mode.
3. Choose **Load unpacked** and select `packages/browser-extension`.
4. Start daari (`daari serve`) and open extension popup.
