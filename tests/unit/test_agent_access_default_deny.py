"""Opt-in agent_access_default_deny for multi_agent virtual keys (#2004)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.agent_access import (
    key_has_agent_grant,
    virtual_key_lacks_agent_grant,
)
from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import AuthClaims


def _key(metadata=None) -> VirtualKey:
    return VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_abc",
        metadata=metadata or {},
    )


def _claims(metadata=None, *, kind: str = "virtual") -> AuthClaims:
    if kind == "master":
        return AuthClaims(kind="master")
    key = _key(metadata)
    return AuthClaims(kind="virtual", key_id=key.key_id, client_id="agent", virtual_key=key)


class TestKeyHasAgentGrant:
    def test_missing_is_not_a_grant(self):
        assert key_has_agent_grant({}) is False
        assert key_has_agent_grant({"other": 1}) is False
        assert key_has_agent_grant({"agents_access": False}) is False
        assert key_has_agent_grant(None) is False

    def test_agents_access_true(self):
        assert key_has_agent_grant({"agents_access": True}) is True

    def test_allowed_agents_list(self):
        assert key_has_agent_grant({"allowed_agents": ["multi_agent"]}) is True
        assert key_has_agent_grant({"allowed_agents": []}) is True
        assert key_has_agent_grant({"allowed_agents": "*"}) is True


class TestAgentAccessDefaultDenyFlag:
    def test_flag_defaults_off(self):
        settings = Settings()
        assert settings.server.virtual_keys.agent_access_default_deny is False

    def test_flag_off_never_lacks_grant(self):
        settings = Settings()
        assert virtual_key_lacks_agent_grant(_claims({}), settings) is False

    def test_flag_on_vk_without_grant(self):
        settings = Settings.model_validate(
            {"server": {"virtual_keys": {"agent_access_default_deny": True}}}
        )
        assert virtual_key_lacks_agent_grant(_claims({}), settings) is True
        assert virtual_key_lacks_agent_grant(_claims({"other": 1}), settings) is True

    def test_flag_on_vk_with_grant_ok(self):
        settings = Settings.model_validate(
            {"server": {"virtual_keys": {"agent_access_default_deny": True}}}
        )
        assert (
            virtual_key_lacks_agent_grant(_claims({"agents_access": True}), settings) is False
        )
        assert (
            virtual_key_lacks_agent_grant(
                _claims({"allowed_agents": ["multi_agent"]}), settings
            )
            is False
        )

    def test_master_and_anonymous_unchanged(self):
        settings = Settings.model_validate(
            {"server": {"virtual_keys": {"agent_access_default_deny": True}}}
        )
        assert virtual_key_lacks_agent_grant(_claims(kind="master"), settings) is False
        assert virtual_key_lacks_agent_grant(None, settings) is False


def _vk_app(settings, *, metadata=None):
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", metadata=metadata)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, {"Authorization": f"Bearer {created.plaintext}"}


def _agent_denied_count(app) -> int:
    metrics = app.state.ctx.metrics
    snap = metrics.snapshot(include_histograms=True)
    return int(snap.get("agent_access_denied") or 0)


@pytest.mark.asyncio
async def test_multi_agent_denied_when_vk_lacks_grant(settings, monkeypatch):
    settings.server.virtual_keys.agent_access_default_deny = True
    settings.frontier.enabled = True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "gpt-6.1-sol",
                "input": "delegate",
                "multi_agent": {"enabled": True},
            },
        )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert "agent" in str(detail).lower() or "grant" in str(detail).lower()
    assert _agent_denied_count(app) == 1
    assert "daari_agent_access_denied_total 1" in render_prometheus(app.state.ctx.metrics)


@pytest.mark.asyncio
async def test_multi_agent_ok_when_vk_has_grant(settings, monkeypatch):
    settings.server.virtual_keys.agent_access_default_deny = True
    settings.frontier.enabled = True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app, headers = _vk_app(settings, metadata={"agents_access": True})

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L6", executor="openai", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    # Ensure frontier looks enabled so we get past the frontier gate after grant.
    app.state.ctx.router.frontier_enabled = True
    app.state.ctx.router.frontier = type("F", (), {"api_key": "sk-test"})()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "gpt-6.1-sol",
                "input": "delegate",
                "multi_agent": {"enabled": True},
            },
        )
    assert response.status_code != 403
    assert _agent_denied_count(app) == 0


@pytest.mark.asyncio
async def test_multi_agent_passthrough_when_flag_off(settings):
    assert settings.server.virtual_keys.agent_access_default_deny is False
    settings.frontier.enabled = False
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "daari",
                "input": "delegate",
                "multi_agent": {"enabled": True},
            },
        )
    # Flag off → not 403; frontier-disabled still 400 as today.
    assert response.status_code != 403
    assert _agent_denied_count(app) == 0


@pytest.mark.asyncio
async def test_stats_json_exposes_agent_access_denied(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json().get("agent_access_denied", 0) == 0
        app.state.ctx.metrics.record_agent_access_denied()
        after = await client.get("/v1/daari/stats")
    assert after.json()["agent_access_denied"] == 1


@pytest.mark.asyncio
async def test_agent_access_denied_noop_when_prometheus_disabled(settings, monkeypatch):
    settings.observability.prometheus = False
    settings.server.virtual_keys.agent_access_default_deny = True
    settings.frontier.enabled = True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "gpt-6.1-sol",
                "input": "delegate",
                "multi_agent": {"enabled": True},
            },
        )
    assert denied.status_code == 403
    assert _agent_denied_count(app) == 0
