"""Per-key / per-team service_tier allowlist (#2070)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.service_tier_access import (
    effective_allowed_service_tiers,
    service_tier_permitted,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def test_merge_is_most_restrictive_intersection():
    assert effective_allowed_service_tiers(None, None) is None
    assert effective_allowed_service_tiers(["default", "flex"], None) == ("default", "flex")
    assert effective_allowed_service_tiers(None, ["default"]) == ("default",)
    assert effective_allowed_service_tiers(
        ["default", "priority", "flex"],
        ["default", "flex"],
    ) == ("default", "flex")
    assert service_tier_permitted("priority", allowed=("default", "flex")) is False
    assert service_tier_permitted("default", allowed=("default", "flex")) is True
    assert service_tier_permitted("ultrafast", allowed=None) is True
    assert service_tier_permitted(None, allowed=("default",)) is True
    assert service_tier_permitted("", allowed=("default",)) is True


def test_store_round_trip_via_metadata(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team(
        "eng",
        allowed_service_tiers=["default", "flex"],
        degrade_disallowed_service_tier=True,
    )
    created = store.create(
        "ci",
        team="eng",
        allowed_service_tiers=["default"],
    )
    found = store.resolve(created.plaintext)
    assert found is not None
    assert found.allowed_service_tiers == ("default",)
    assert found.degrade_disallowed_service_tier is False
    loaded = store.get_team(team.team_id)
    assert loaded is not None
    assert loaded.allowed_service_tiers == ("default", "flex")
    assert loaded.degrade_disallowed_service_tier is True
    assert store.update_service_tier_access(
        created.key.key_id,
        allowed_service_tiers=["default", "priority"],
        degrade_disallowed_service_tier=True,
    )
    updated = store.resolve(created.plaintext)
    assert updated is not None
    assert updated.allowed_service_tiers == ("default", "priority")
    assert updated.degrade_disallowed_service_tier is True
    open_key = store.create("open")
    assert store.resolve(open_key.plaintext).allowed_service_tiers is None


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        warning = getattr(request.sampling, "gate_warning", None)
        return InternalResponse(
            content="ok",
            model=request.model or "llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
                warning=warning,
                service_tier=request.sampling.service_tier,
            ),
        )

    app.state.ctx.router.route = fake
    app.state.ctx.router.ollama.execute = fake


@pytest.mark.asyncio
async def test_gateway_deny_degrade_and_passthrough(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", allowed_service_tiers=["default", "flex", "fast", "standard"])
    locked = store.create(
        "locked",
        client_id="locked",
        team="eng",
        allowed_service_tiers=["default", "fast", "standard"],
    )
    degrade_key = store.create(
        "degrade",
        client_id="degrade",
        allowed_service_tiers=["default"],
        degrade_disallowed_service_tier=True,
    )
    open_key = store.create("open", client_id="open")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deny_headers = {
            "Authorization": f"Bearer {locked.plaintext}",
            "X-Daari-No-Cache": "true",
        }
        for path, body in (
            (
                "/v1/chat/completions",
                {
                    "model": "llama3.2:3b",
                    "messages": [{"role": "user", "content": "hi"}],
                    "service_tier": "priority",
                },
            ),
            (
                "/v1/responses",
                {"model": "llama3.2:3b", "input": "hi", "service_tier": "priority"},
            ),
            (
                "/v1/messages",
                {
                    "model": "llama3.2:3b",
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "hi"}],
                    "speed": "fast",
                },
            ),
        ):
            # messages speed=fast is allowed for locked (intersect includes fast)
            if path == "/v1/messages":
                ok_msg = await client.post(path, json=body, headers=deny_headers)
                assert ok_msg.status_code == 200, (path, ok_msg.text)
                continue
            denied = await client.post(path, json=body, headers=deny_headers)
            assert denied.status_code == 403, (path, denied.status_code, denied.text)
            assert "service_tier_not_allowed" in denied.text

        # Anthropic speed deny when not on allowlist
        speed_denied = await client.post(
            "/v1/messages",
            json={
                "model": "llama3.2:3b",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "hi"}],
                "speed": "fast",
                "service_tier": "priority",
            },
            headers={
                "Authorization": f"Bearer {store.create('no-fast', allowed_service_tiers=['default']).plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        # service_tier on messages may be ignored; speed=fast is the check
        # Key only allows default — fast should 403
        assert speed_denied.status_code == 403, speed_denied.text
        assert "service_tier_not_allowed" in speed_denied.text

        degraded = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
                "service_tier": "priority",
            },
            headers={
                "Authorization": f"Bearer {degrade_key.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert degraded.status_code == 200, degraded.text
        payload = degraded.json()
        assert "service_tier_not_allowed_degraded" in (
            (payload.get("daari_meta") or {}).get("warning") or ""
        )

        passthrough = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
                "service_tier": "priority",
            },
            headers={
                "Authorization": f"Bearer {open_key.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert passthrough.status_code == 200, passthrough.text
        assert "service_tier_not_allowed" not in (
            (passthrough.json().get("daari_meta") or {}).get("warning") or ""
        )
