"""Gateway ASGI pin for server.header_policy deny + open-probe exemption (#1197).

Hermetic (mocked) coverage under tests/integration/ — same convention as other
non-@integration modules here. Unit evaluate_* cases live in
tests/unit/test_header_policy.py; this file pins the live middleware path.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import HeaderDenyRule, HeaderPolicySettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_header_policy_deny_and_health_exempt(settings, monkeypatch):
    """Denied chat returns header_policy_error; /health stays open (#1197)."""
    settings.server.api_key = "master"
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        deny=[HeaderDenyRule(header="user-agent", exact="BadBot/1.0")],
    )
    called = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        called["n"] += 1
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    application = _app(settings)
    monkeypatch.setattr(application.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            headers={
                **META_HEADERS,
                "Authorization": "Bearer master",
                "User-Agent": "BadBot/1.0",
            },
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )
        health = await client.get("/health", headers={"User-Agent": "BadBot/1.0"})

    assert denied.status_code == 403
    err = denied.json()["error"]
    assert err["type"] == "header_policy_error"
    assert err["code"] == "header_denied"
    assert called["n"] == 0

    assert health.status_code == 200
    body = health.json()
    assert body.get("error", {}).get("type") != "header_policy_error"
