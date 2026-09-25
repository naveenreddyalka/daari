"""Endpoint-family RPM/TPM on virtual keys (#1099)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import family_limits_from_key, rate_limit_family
from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app


def test_rate_limit_family_maps_paths():
    assert rate_limit_family("/v1/chat/completions") == "chat"
    assert rate_limit_family("/v1/embeddings") == "embeddings"
    assert rate_limit_family("/v1/images/generations") == "images"
    assert rate_limit_family("/v1/images/variations") == "images"
    assert rate_limit_family("/v1/audio/speech") == "audio"
    assert rate_limit_family("/v1/moderations") == "moderations"
    assert rate_limit_family("/v1/rerank") == "rerank"
    assert rate_limit_family("/health") == "other"


def test_family_limits_from_key_metadata():
    key = VirtualKey(
        key_id="k1",
        name="n",
        prefix="dk_x",
        metadata={"rate_families": {"images": {"rpm": 2, "tpm": 100}, "chat": {"rpm": 10}}},
    )
    assert family_limits_from_key(key, "images") == (2, 100)
    assert family_limits_from_key(key, "chat") == (10, 0)
    assert family_limits_from_key(key, "embeddings") == (0, 0)
    assert family_limits_from_key(None, "chat") == (0, 0)


def test_family_rpm_independent_of_other_families():
    limiter = RateLimiter(backend=MemoryCounterBackend(), default_rpm=0, default_tpm=0)
    # Exhaust images family.
    assert limiter.check(
        key_id="alice", model="m", tokens=1, family="images", family_rpm=1
    ).allowed
    denied = limiter.check(
        key_id="alice", model="m", tokens=1, family="images", family_rpm=1
    )
    assert not denied.allowed
    assert denied.bucket == "family:images"
    # Chat still open on the same key.
    ok = limiter.check(key_id="alice", model="m", tokens=1, family="chat", family_rpm=1)
    assert ok.allowed


def test_parse_rate_family_flag():
    from daari.cli.app import parse_rate_family_flag

    assert parse_rate_family_flag("images:10") == ("images", {"rpm": 10})
    assert parse_rate_family_flag("chat:60:40000") == ("chat", {"rpm": 60, "tpm": 40000})
    with pytest.raises(ValueError, match="unknown"):
        parse_rate_family_flag("widgets:1")


@pytest.mark.asyncio
async def test_gateway_family_quota_429_leaves_other_family(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.rate_limit.rpm = 0
    settings.rate_limit.tpm = 0
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create(
        "scoped",
        metadata={"rate_families": {"images": {"rpm": 1}}},
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {"Authorization": f"Bearer {created.plaintext}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/images/generations",
            json={"prompt": "a"},
            headers=headers,
        )
        second = await client.post(
            "/v1/images/generations",
            json={"prompt": "b"},
            headers=headers,
        )
        chat = await client.post(
            "/v1/chat/completions",
            json={"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hi"}]},
            headers=headers,
        )

    # First images call may 501 (frontier off) but still counts against RPM.
    assert first.status_code in {200, 501}
    assert second.status_code == 429
    assert "family:images" in second.json()["error"]["message"]
    assert second.headers.get("X-RateLimit-Scope") == "family:images"
    # Chat is a different family — not blocked by the images ceiling.
    assert chat.status_code != 429
