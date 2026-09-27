"""POST /v1/responses/compact (#1153)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.response_store import ResponseStore
from daari.router.router import AppContext
from daari.server.app import create_app

DOC = Path(__file__).resolve().parents[2] / "docs/developer/concepts/clients-and-gateways.md"
HTTP_API = Path(__file__).resolve().parents[2] / "docs/developer/reference/http-api.md"


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _store(settings) -> ResponseStore:
    path = Path(settings.trace.path).expanduser().parent / "responses.sqlite3"
    return ResponseStore(path)


def test_docs_mention_responses_compact():
    concepts = DOC.read_text(encoding="utf-8")
    api = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/responses/compact" in concepts or "responses/compact" in concepts
    assert "/v1/responses/compact" in api


@pytest.mark.asyncio
async def test_compact_from_previous_response_id(settings):
    app = _app(settings)
    long_conv = [{"role": "user", "content": f"turn {i} " + ("x" * 40)} for i in range(12)]
    _store(settings).put(
        "resp_long",
        {"id": "resp_long", "status": "completed", "output": [], "model": "m"},
        conversation=long_conv,
        stored=True,
    )

    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last = request
        return InternalResponse(
            content="short summary of the prior turns",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=2),
        )

    app.state.ctx.router.route = fake_route

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.post(
            "/v1/responses/compact",
            json={"model": "daari", "previous_response_id": "resp_missing"},
        )
        response = await client.post(
            "/v1/responses/compact",
            json={"model": "daari", "previous_response_id": "resp_long", "store": True},
        )

    assert missing.status_code == 404
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["id"] != "resp_long"
    assert "short summary" in body["output"][0]["content"][0]["text"]
    stored = _store(settings).get(body["id"])
    assert stored is not None
    conv = stored["_conversation"]
    assert len(conv) < len(long_conv)
    assert any("summary" in (m.get("content") or "").lower() for m in conv)
    assert getattr(fake_route, "last", None) is not None


@pytest.mark.asyncio
async def test_compact_requires_input_or_previous(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/responses/compact", json={"model": "daari"})
    assert response.status_code == 400
