#!/usr/bin/env python3
"""Live/smoke verification for web-ui API-key auth (issue #141) — pass 3/3.

Checks:
1. Dashboard HTML ships an `#api-key` field (static bundle).
2. Daemon config editor requires Bearer when `server.api_key` is set (same
   contract the web-ui Authorization header uses).

Usage:
  python scripts/smoke_webui_auth.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from daari.config.settings import Settings
    from daari.router.router import AppContext
    from daari.server.app import create_app

    index = ROOT / "packages" / "web-ui" / "index.html"
    html = index.read_text(encoding="utf-8")
    assert 'id="api-key"' in html, "web-ui index.html missing #api-key field"

    app_js = (ROOT / "packages" / "web-ui" / "app.js").read_text(encoding="utf-8")
    assert "daari.webui.apiKey" in app_js
    assert "Authorization" in app_js and "Bearer" in app_js

    settings = Settings()
    settings.server.api_key = "smoke-master"
    settings.observability.config_editor = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/v1/daari/config")
        assert denied.status_code == 401, denied.status_code

        ok = await client.get(
            "/v1/daari/config",
            headers={"Authorization": "Bearer smoke-master"},
        )
        assert ok.status_code == 200, (ok.status_code, ok.text)
        assert "routing" in ok.json()

        patch = await client.patch(
            "/v1/daari/config",
            headers={
                "Authorization": "Bearer smoke-master",
                "Content-Type": "application/json",
            },
            json={"routing": {"prefer": "latency"}},
        )
        assert patch.status_code == 200, (patch.status_code, patch.text)

    print("PASS smoke_webui_auth: #api-key present; config 401/200 + PATCH with Bearer")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
