"""Pre-auth request-header allow/block policy (#1112)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import HeaderDenyRule, HeaderPolicySettings, Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.header_policy import (
    OPEN_HEADER_POLICY_PATHS,
    evaluate_header_policy,
    header_policy_active,
)
from tests.conftest import META_HEADERS


def test_header_policy_defaults_off() -> None:
    policy = Settings().server.header_policy
    assert isinstance(policy, HeaderPolicySettings)
    assert policy.enabled is False
    assert policy.required == []
    assert policy.deny == []
    assert policy.allow == {}
    assert not header_policy_active(policy)


def test_evaluate_required_missing() -> None:
    policy = HeaderPolicySettings(enabled=True, required=["X-Client-Id"])
    decision = evaluate_header_policy(policy, {})
    assert decision is not None
    assert decision.code == "header_required"
    assert decision.status_code == 400


def test_evaluate_deny_exact() -> None:
    policy = HeaderPolicySettings(
        enabled=True,
        deny=[HeaderDenyRule(header="user-agent", exact="BadBot/1.0")],
    )
    decision = evaluate_header_policy(policy, {"user-agent": "BadBot/1.0"})
    assert decision is not None
    assert decision.code == "header_denied"
    assert decision.status_code == 403


def test_evaluate_deny_regex() -> None:
    policy = HeaderPolicySettings(
        enabled=True,
        deny=[HeaderDenyRule(header="user-agent", regex=r"(?i)scrapy")],
    )
    decision = evaluate_header_policy(policy, {"user-agent": "python-scrapy/2.0"})
    assert decision is not None
    assert decision.code == "header_denied"


def test_evaluate_allowlist_rejects_other() -> None:
    policy = HeaderPolicySettings(
        enabled=True,
        allow={"x-daari-env": ["prod", "staging"]},
    )
    decision = evaluate_header_policy(policy, {"x-daari-env": "dev"})
    assert decision is not None
    assert decision.code == "header_not_allowed"
    assert decision.status_code == 403


def test_evaluate_allow_when_clean() -> None:
    policy = HeaderPolicySettings(
        enabled=True,
        required=["X-Client-Id"],
        deny=[HeaderDenyRule(header="user-agent", exact="BadBot")],
        allow={"x-daari-env": ["prod"]},
    )
    decision = evaluate_header_policy(
        policy,
        {
            "x-client-id": "cursor",
            "user-agent": "curl/8.0",
            "x-daari-env": "prod",
        },
    )
    assert decision is None


def _app(settings: Settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_disabled_policy_is_noop(settings, monkeypatch):
    settings.server.api_key = "master"
    settings.server.header_policy = HeaderPolicySettings(
        enabled=False,
        deny=[HeaderDenyRule(header="user-agent", exact="BadBot")],
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
        response = await client.post(
            "/v1/chat/completions",
            headers={
                **META_HEADERS,
                "Authorization": "Bearer master",
                "User-Agent": "BadBot",
            },
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert called["n"] == 1


@pytest.mark.asyncio
async def test_deny_blocks_before_auth(settings, monkeypatch):
    """Junk UA is rejected without reaching the router (auth never succeeds)."""
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
        # Wrong key would normally 401; policy must win with 403 first.
        response = await client.post(
            "/v1/chat/completions",
            headers={
                **META_HEADERS,
                "Authorization": "Bearer wrong-key",
                "User-Agent": "BadBot/1.0",
            },
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["type"] == "header_policy_error"
    assert body["error"]["code"] == "header_denied"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_missing_required_returns_400(settings, monkeypatch):
    settings.server.api_key = "master"
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        required=["X-Client-Id"],
    )
    application = _app(settings)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={"Authorization": "Bearer master"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "header_required"


@pytest.mark.asyncio
async def test_open_paths_exempt(settings):
    settings.server.api_key = "master"
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        required=["X-Client-Id"],
        deny=[HeaderDenyRule(header="user-agent", exact="BadBot")],
    )
    application = _app(settings)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/health", "/ready", "/v1/messages/health", "/metrics"):
            assert path in OPEN_HEADER_POLICY_PATHS
            response = await client.get(path, headers={"User-Agent": "BadBot"})
            err = response.json().get("error") if response.headers.get(
                "content-type", ""
            ).startswith("application/json") else None
            if isinstance(err, dict):
                assert err.get("type") != "header_policy_error", path
            assert response.status_code not in {400, 403} or (
                isinstance(err, dict) and err.get("type") != "header_policy_error"
            ), (path, response.status_code, response.text[:200])


@pytest.mark.asyncio
async def test_allowlist_blocks_disallowed_value(settings):
    settings.server.api_key = "master"
    settings.server.header_policy = HeaderPolicySettings(
        enabled=True,
        allow={"x-tenant": ["acme"]},
    )
    application = _app(settings)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={
                "Authorization": "Bearer master",
                "X-Tenant": "other",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "header_not_allowed"
