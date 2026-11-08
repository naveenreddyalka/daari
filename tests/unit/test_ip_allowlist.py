"""Per-key / per-team client IP allowlist (#2144)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.ip_access import (
    client_ip_allowed,
    coerce_ips,
    ip_permitted,
)
from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore
from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def test_coerce_and_match_ipv4_cidr_and_ipv6():
    assert coerce_ips(None) is None
    assert coerce_ips(["203.0.113.0/24"]) == ("203.0.113.0/24",)
    assert coerce_ips(["2001:db8::1"]) == ("2001:db8::1/128",)
    assert ip_permitted("203.0.113.10", allowed=("203.0.113.0/24",)) is True
    assert ip_permitted("198.51.100.1", allowed=("203.0.113.0/24",)) is False
    assert ip_permitted("2001:db8::1", allowed=("2001:db8::/64",)) is True
    assert ip_permitted("2001:db8:1::1", allowed=("2001:db8::/64",)) is False
    assert ip_permitted("203.0.113.10", allowed=None) is True
    with pytest.raises(ValueError, match="invalid"):
        coerce_ips(["not-an-ip"])


def test_key_and_team_lists_both_checked():
    assert client_ip_allowed(
        "203.0.113.10",
        key_ips=("203.0.113.0/24",),
        team_ips=("203.0.113.0/24",),
    )
    assert not client_ip_allowed(
        "203.0.113.10",
        key_ips=("203.0.113.0/24",),
        team_ips=("198.51.100.0/24",),
    )
    assert not client_ip_allowed(
        "203.0.113.10",
        key_ips=("198.51.100.0/24",),
        team_ips=("203.0.113.0/24",),
    )
    assert client_ip_allowed("203.0.113.10", key_ips=None, team_ips=None)


def test_store_round_trip_sqlite_and_rotate(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", allowed_ips=["203.0.113.0/24"])
    created = store.create(
        "ci",
        team="eng",
        allowed_ips=["203.0.113.10", "2001:db8::/64"],
    )
    found = store.resolve(created.plaintext)
    assert found is not None
    assert found.allowed_ips == ("203.0.113.10/32", "2001:db8::/64")
    loaded = store.get_team(team.team_id)
    assert loaded is not None
    assert loaded.allowed_ips == ("203.0.113.0/24",)
    assert store.update_ip_access(
        created.key.key_id,
        allowed_ips=["198.51.100.0/24"],
    )
    updated = store.resolve(created.plaintext)
    assert updated is not None
    assert updated.allowed_ips == ("198.51.100.0/24",)
    rotated = store.rotate(created.key.key_id, grace="1h")
    after = store.resolve(rotated.plaintext)
    assert after is not None
    assert after.allowed_ips == ("198.51.100.0/24",)
    open_key = store.create("open")
    assert store.resolve(open_key.plaintext).allowed_ips is None
    with pytest.raises(ValueError, match="invalid"):
        store.create("bad", allowed_ips=["999.999.999.999"])


def test_store_round_trip_postgres():
    store = PostgresVirtualKeyStore(f"memory:ip-allow-{id(object())}")
    team = store.create_team("ops", allowed_ips=["10.0.0.0/8"])
    created = store.create("bot", team="ops", allowed_ips=["10.1.2.3"])
    found = store.resolve(created.plaintext)
    assert found is not None
    assert found.allowed_ips == ("10.1.2.3/32",)
    assert store.get_team(team.team_id).allowed_ips == ("10.0.0.0/8",)
    assert store.update_ip_access(created.key.key_id, allowed_ips=["10.9.0.0/16"])
    assert store.resolve(created.plaintext).allowed_ips == ("10.9.0.0/16",)
    assert store.update_team_ip_access(team.team_id, allowed_ips=["10.0.0.0/16"])
    assert store.get_team(team.team_id).allowed_ips == ("10.0.0.0/16",)


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model or "llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake
    app.state.ctx.router.ollama.execute = fake


@pytest.mark.asyncio
async def test_gateway_deny_and_passthrough(settings, tmp_path, monkeypatch):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.observability.prometheus = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", allowed_ips=["203.0.113.0/24"])
    locked = store.create(
        "locked",
        client_id="locked",
        team="eng",
        allowed_ips=["203.0.113.0/24"],
    )
    open_key = store.create("open", client_id="open")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)

    from daari.auth import invalid_key_throttle

    monkeypatch.setattr(
        invalid_key_throttle,
        "client_ip_from_request",
        lambda _req: "198.51.100.50",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "Authorization": f"Bearer {locked.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert denied.status_code == 403, denied.text
        assert "ip_not_allowed" in denied.text
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
        assert 'daari_rejects_total{kind="ip_not_allowed"} 1' in metrics.text

        monkeypatch.setattr(
            invalid_key_throttle,
            "client_ip_from_request",
            lambda _req: "203.0.113.20",
        )
        ok = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "Authorization": f"Bearer {locked.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert ok.status_code == 200, ok.text

        monkeypatch.setattr(
            invalid_key_throttle,
            "client_ip_from_request",
            lambda _req: "198.51.100.50",
        )
        passthrough = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={
                "Authorization": f"Bearer {open_key.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert passthrough.status_code == 200, passthrough.text

    audit = audit_log_from_settings(settings)
    actions = {row["action"] for row in audit.list(limit=50)}
    assert "auth.ip_not_allowed" in actions
