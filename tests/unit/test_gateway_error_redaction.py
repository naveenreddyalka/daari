"""Client-facing gateway errors must not leak registered secrets (#412)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.client_errors import (
    routing_failure_detail,
    safe_detail,
    summarize_upstream_failure,
)
from daari.gateway.internal import InternalRequest, InternalResponse
from daari.security.secret_refs import clear_registered_secrets, register_secret
from daari.server.app import AppContext, create_app


@pytest.fixture(autouse=True)
def _clear_secrets():
    clear_registered_secrets()
    yield
    clear_registered_secrets()


def test_safe_detail_redacts_registered_secret():
    register_secret("sk-live-super-secret")
    assert "sk-live-super-secret" not in safe_detail("boom sk-live-super-secret boom")
    assert "[redacted]" in safe_detail("boom sk-live-super-secret boom")


def test_http_status_error_is_summarized_without_url():
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/chat/completions?api_key=sk-live-super-secret",
    )
    response = httpx.Response(502, request=request, text="upstream blew up")
    exc = httpx.HTTPStatusError("bad", request=request, response=response)
    register_secret("sk-live-super-secret")
    summary = summarize_upstream_failure(exc)
    assert "api.openai.com" in summary
    assert "502" in summary
    assert "sk-live-super-secret" not in summary
    assert "chat/completions" not in summary
    detail = routing_failure_detail(exc)
    assert detail.startswith("Routing failed:")
    assert "sk-live-super-secret" not in detail


@pytest.mark.asyncio
async def test_routing_failure_response_redacts_secret(settings, tmp_path):
    register_secret("sk-leaked-provider-key")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    async def explode(request: InternalRequest) -> InternalResponse:
        raise RuntimeError("provider rejected key sk-leaked-provider-key")

    application.state.ctx.router.route = explode  # type: ignore[method-assign]

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 503
    body = response.text
    assert "sk-leaked-provider-key" not in body
    assert "[redacted]" in body
    assert "Routing failed:" in body
