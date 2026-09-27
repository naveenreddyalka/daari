"""POST /v1/responses/compact (#1153, #1169)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.response_store import ResponseStore
from daari.observability.usage import UsageLedger
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


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.trace.path = str(tmp_path / "trace.jsonl")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


@pytest.mark.asyncio
async def test_compact_applies_auth_claims_to_meta(settings, tmp_path):
    """Compact must fence like /v1/responses — tier_cap, key/team attribution (#1169)."""
    app, store, _ledger = _app_with_keys(settings, tmp_path)
    team = store.create_team("eng")
    created = store.create(
        "capped",
        client_id="capped-client",
        team="eng",
        tier_cap="L5",
        metadata={"no_frontier": True},
        allowed_models=["llama*"],
    )
    long_conv = [{"role": "user", "content": f"turn {i} " + ("x" * 40)} for i in range(12)]
    _store(settings).put(
        "resp_long",
        {"id": "resp_long", "status": "completed", "output": [], "model": "m"},
        conversation=long_conv,
        stored=True,
        owner_key_id=created.key.key_id,
    )

    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last = request
        return InternalResponse(
            content="summary",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=2),
        )

    app.state.ctx.router.route = fake_route
    headers = {"Authorization": f"Bearer {created.plaintext}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/responses/compact",
            json={"model": "gpt-4o", "previous_response_id": "resp_long"},
            headers=headers,
        )
        ok = await client.post(
            "/v1/responses/compact",
            json={"model": "llama3.2:3b", "previous_response_id": "resp_long"},
            headers=headers,
        )

    assert denied.status_code == 403
    assert "model_not_allowed" in denied.text
    assert ok.status_code == 200, ok.text
    meta = fake_route.last.meta
    assert meta.tier_cap == "L5"
    assert meta.no_frontier is True
    assert meta.key_id == created.key.key_id
    assert meta.team_id == team.team_id
    assert meta.client_id == "capped-client"


@pytest.mark.asyncio
async def test_compact_enforces_model_max_budget(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    store.create_team("eng", model_max_budget={"gpt-4*": 1.0})
    created = store.create(
        "a",
        client_id="key-a",
        team="eng",
        model_max_budget={"gpt-4*": 1.0},
    )
    ledger.record(
        tier="L6",
        client_id="key-a",
        model="gpt-4-custom",
        input_tokens=int(1.05 / 0.002 * 1000),
        output_tokens=0,
    )
    long_conv = [{"role": "user", "content": "turn " + ("x" * 40)} for _ in range(12)]
    _store(settings).put(
        "resp_bud",
        {"id": "resp_bud", "status": "completed", "output": [], "model": "m"},
        conversation=long_conv,
        stored=True,
        owner_key_id=created.key.key_id,
    )

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="summary",
            model="gpt-4-custom",
            daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=2),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hard = await client.post(
            "/v1/responses/compact",
            json={"model": "gpt-4-custom", "previous_response_id": "resp_bud"},
            headers={"Authorization": f"Bearer {created.plaintext}"},
        )
    assert hard.status_code == 402
    err = hard.json()["error"]
    assert err["type"] == "budget_exceeded"
    assert err["scope"] == "model"
    assert err["model_pattern"] == "gpt-4*"
