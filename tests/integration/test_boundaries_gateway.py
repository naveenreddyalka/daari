"""Integration: product boundary gate via OpenAI gateway (issue #145 / F6).

Verification pass 2/3 — ASGI chat completions with boundaries enabled.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _enable_fintech(settings, *, mode: str = "block") -> None:
    settings.boundaries.enabled = True
    settings.boundaries.mode = mode
    settings.boundaries.product_name = "CK Assist"
    settings.boundaries.product_description = "Credit scores and cards only."
    settings.boundaries.allow_topics = ["credit score", "credit card", "loan"]
    settings.boundaries.deny_topics = ["python", "wedding", "novel"]
    settings.boundaries.examples_in = ["Why did my score drop?"]
    settings.boundaries.examples_out = ["Write a Python scraper"]
    settings.boundaries.refuse_message = "I only help with credit questions."
    settings.boundaries.clear_out_threshold = 0.7
    settings.boundaries.clear_in_threshold = 0.7
    settings.boundaries.stages_b0 = True
    settings.boundaries.stages_b1 = True
    settings.boundaries.stages_b2 = False
    settings.boundaries.stages_b3 = False


def _app_with_fake_model(settings):
    calls = {"n": 0}
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content="model-ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    for ex in (ctx.router.ollama, ctx.router.ollama_l3, ctx.router.ollama_l4, ctx.router.ollama_l5):
        ex.execute = fake_execute  # type: ignore[method-assign]
    app.state.ctx = ctx
    return app, calls


@pytest.mark.asyncio
async def test_gateway_blocks_out_of_scope_without_model(settings):
    _enable_fintech(settings, mode="block")
    app, calls = _app_with_fake_model(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Write a Python scraper"}],
            },
            headers=META_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daari_meta"]["tier"] == "boundary"
    assert body["daari_meta"]["boundary"]["label"] == "out"
    assert body["daari_meta"]["boundary"]["stage"] == "b0"
    assert "credit" in body["choices"][0]["message"]["content"].lower()
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_gateway_allows_in_scope(settings):
    _enable_fintech(settings, mode="block")
    app, calls = _app_with_fake_model(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [
                    {"role": "user", "content": "Why did my credit score drop?"}
                ],
            },
            headers=META_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daari_meta"]["tier"] in ("L3", "L4", "L5")
    assert body["daari_meta"]["boundary"]["label"] == "in"
    assert "model-ok" in body["choices"][0]["message"]["content"]
    assert calls["n"] >= 1


@pytest.mark.asyncio
async def test_gateway_warn_mode_answers_but_annotates(settings):
    _enable_fintech(settings, mode="warn")
    app, calls = _app_with_fake_model(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Plan my wedding"}],
            },
            headers=META_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daari_meta"]["tier"] in ("L3", "L4", "L5")
    assert body["daari_meta"]["boundary"]["label"] == "out"
    assert body["daari_meta"]["warning"]
    assert "model-ok" in body["choices"][0]["message"]["content"]
    assert calls["n"] >= 1


@pytest.mark.asyncio
async def test_gateway_disabled_skips_boundary(settings):
    settings.boundaries.enabled = False
    app, calls = _app_with_fake_model(settings)
    assert app.state.ctx.router.boundaries is None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Write a Python scraper"}],
            },
            headers=META_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daari_meta"].get("boundary") is None
    assert body["daari_meta"]["tier"] != "boundary"
    assert calls["n"] >= 1


@pytest.mark.asyncio
async def test_gateway_boundary_profile_header_selects_overlay(settings):
    """X-Daari-Boundary-Profile applies a named overlay (#171)."""
    settings.boundaries.enabled = False
    settings.boundaries.mode = "block"
    settings.boundaries.allow_topics = []
    settings.boundaries.deny_topics = []
    settings.boundaries.profiles = {
        "fintech-assist": {
            "allow_topics": ["credit score", "credit card"],
            "deny_topics": ["wedding", "novel"],
            "refuse_message": "I only help with credit questions.",
            "clear_out_threshold": 0.7,
            "clear_in_threshold": 0.7,
            "stages_b0": True,
            "stages_b1": True,
        }
    }
    app, calls = _app_with_fake_model(settings)
    assert app.state.ctx.router.boundaries is not None
    transport = ASGITransport(app=app)
    headers = {**META_HEADERS, "X-Daari-Boundary-Profile": "fintech-assist"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        blocked = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Plan my wedding"}],
            },
            headers=headers,
        )
        allowed = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Why did my credit score drop?"}],
            },
            headers=headers,
        )
    assert blocked.status_code == 200
    assert blocked.json()["daari_meta"]["tier"] == "boundary"
    assert allowed.status_code == 200
    assert allowed.json()["daari_meta"]["tier"] in ("L3", "L4", "L5")
    assert calls["n"] >= 1


@pytest.mark.asyncio
async def test_config_patch_rebuilds_boundary_engine(settings):
    settings.observability.config_editor = True
    _enable_fintech(settings, mode="warn")
    app, _calls = _app_with_fake_model(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patched = await client.patch(
            "/v1/daari/config",
            json={
                "boundaries": {
                    "mode": "block",
                    "deny_topics": ["python", "scraping"],
                    "refuse_message": "Nope — credit only.",
                }
            },
        )
        assert patched.status_code == 200
        assert patched.json()["boundaries"]["mode"] == "block"

        blocked = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "Write a Python scraper"}],
            },
            headers=META_HEADERS,
        )
    assert blocked.status_code == 200
    body = blocked.json()
    assert body["daari_meta"]["tier"] == "boundary"
    assert "Nope" in body["choices"][0]["message"]["content"]
