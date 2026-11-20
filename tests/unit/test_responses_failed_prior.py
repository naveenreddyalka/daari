"""previous_response_id must not replay failed/cancelled turns (#2255)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.response_store import ResponseStore
from daari.router.router import AppContext
from daari.server.app import create_app

DOC = Path(__file__).resolve().parents[2] / "docs/developer/concepts/clients-and-gateways.md"


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _store(settings) -> ResponseStore:
    path = Path(settings.trace.path).expanduser().parent / "responses.sqlite3"
    return ResponseStore(path)


def _mock_route(app, content="ok"):
    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last_request = request
        return InternalResponse(
            content=content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    return fake_route


def test_docs_reject_failed_previous_response_id():
    text = DOC.read_text(encoding="utf-8")
    assert "failed" in text.lower() and "previous_response_id" in text
    assert "cancelled" in text.lower()
    assert "400" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled"])
async def test_chain_from_failed_or_cancelled_returns_400(settings, status, monkeypatch):
    app = _app(settings)
    _mock_route(app)
    poison = [{"role": "user", "content": "poison turn"}, {"role": "assistant", "content": "half"}]
    _store(settings).put(
        "resp_bad",
        {"id": "resp_bad", "object": "response", "status": status, "output": [], "model": "m"},
        conversation=poison,
        stored=True,
    )
    events: list[tuple[str, dict]] = []

    def capture(name: str, fields: dict | None = None) -> None:
        events.append((name, dict(fields or {})))

    monkeypatch.setattr("daari.gateway.responses.log_gateway_event", capture)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "retry", "previous_response_id": "resp_bad"},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "resp_bad" in detail
    assert status in detail
    assert any(
        name == "responses.previous_response_rejected"
        and fields.get("status") == status
        and fields.get("previous_response_id") == "resp_bad"
        for name, fields in events
    )


@pytest.mark.asyncio
async def test_chain_from_completed_ignores_later_failed_sibling(settings):
    """A completed id stays chainable even if a later failed sibling exists."""
    app = _app(settings)
    fake = _mock_route(app, content="chained")
    store = _store(settings)
    good_conv = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    store.put(
        "resp_ok",
        {"id": "resp_ok", "object": "response", "status": "completed", "output": [], "model": "m"},
        conversation=good_conv,
        stored=True,
    )
    store.put(
        "resp_fail_sibling",
        {
            "id": "resp_fail_sibling",
            "object": "response",
            "status": "failed",
            "previous_response_id": "resp_ok",
            "output": [],
            "model": "m",
        },
        conversation=good_conv
        + [{"role": "user", "content": "bad"}, {"role": "assistant", "content": "broken"}],
        stored=True,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "and then?", "previous_response_id": "resp_ok"},
        )

    assert response.status_code == 200
    roles = [m.role for m in fake.last_request.messages]
    contents = [m.content for m in fake.last_request.messages]
    assert "assistant" in roles
    assert "hello" in contents
    assert "broken" not in contents
