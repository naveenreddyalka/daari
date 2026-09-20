"""Selective L0/L1 invalidation (#770)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.cache.exact import ExactCache, cache_key
from daari.cache.redis_exact import RedisExactCache
from daari.cache.semantic import SemanticCache
from daari.cli.app import app as cli_app
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.router.router import AppContext
from daari.server.app import create_app


class _Embedder:
    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        return [1.0]


class _Redis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    def delete(self, key: str):
        return 1 if self.data.pop(key, None) is not None else 0


def _req(text: str = "hello", model: str = "daari") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model=model)


def _resp(text: str = "world", model: str = "llama") -> InternalResponse:
    return InternalResponse(
        content=text,
        model=model,
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="o", latency_ms=1),
    )


def test_exact_invalidate_by_model_hash_and_all(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    cache.put(_req("a"), _resp("one", "llama"))
    cache.put(_req("b"), _resp("two", "mistral"))
    key = cache_key(_req("a"))
    assert cache.invalidate(model="llama") == 1
    assert cache.get(_req("a")) is None
    assert cache.get(_req("b")) is not None
    assert cache.invalidate(entry_hash=key) == 0
    kept = cache_key(_req("b"))
    assert cache.invalidate(entry_hash=kept) == 1
    assert cache.get(_req("b")) is None
    cache.put(_req("c"), _resp("three", "llama"))
    cache.put(_req("d"), _resp("four", "llama"))
    assert cache.invalidate() == 2
    assert cache.get(_req("c")) is None


def test_redis_invalidate_deletes_keys():
    client = _Redis()
    cache = RedisExactCache("redis://test", client=client, enabled=True)
    cache.put(_req("a"), _resp("one", "llama"))
    cache.put(_req("b"), _resp("two", "mistral"))
    assert cache.invalidate(model="llama") == 1
    assert cache.get(_req("a")) is None
    assert cache.get(_req("b")) is not None
    assert any(key.startswith("daari:l0:") for key in client.data)
    assert cache.invalidate() == 1
    assert client.data == {}


def test_semantic_invalidate_filters_context_key(tmp_path):
    cache = SemanticCache(str(tmp_path / "l1"), _Embedder(), enabled=True)
    cache._save_entries(
        [
            {"context_key": "llama|0||", "answer_hash": "aaa", "response_json": "{}"},
            {"context_key": "mistral|0||", "answer_hash": "bbb", "response_json": "{}"},
        ]
    )
    assert cache.invalidate(model="llama") == 1
    left = cache._load_entries()
    assert [row["answer_hash"] for row in left] == ["bbb"]
    assert cache.invalidate(entry_hash="bbb") == 1
    assert cache._load_entries() == []


@pytest.mark.asyncio
async def test_admin_invalidate_returns_counts_and_logs(settings, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.openai.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.cache.put(_req("cached"), _resp("answer", "llama"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/cache/invalidate",
            json={"model": "llama"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["l0_removed"] == 1
    assert body["removed"] == body["l0_removed"] + body["l1_removed"]
    assert events and events[-1][0] == "cache_invalidate"
    assert app.state.ctx.router.cache.get(_req("cached")) is None


def test_cache_prune_notes_redis_ttl(monkeypatch, settings):
    settings.cache.backend = "redis"
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    result = CliRunner().invoke(cli_app, ["cache", "prune"])
    assert result.exit_code == 0
    assert "Redis relies on TTL" in result.stdout
    assert "does not scan" in result.stdout


def test_cache_invalidate_cli_on_disk(monkeypatch, settings, tmp_path):
    settings.cache.l0.path = str(tmp_path / "l0")
    settings.cache.l1.path = str(tmp_path / "l1")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr("daari.cli.app._daemon_is_running", lambda _settings: False)
    cache = ExactCache(str(settings.l0_cache_path), enabled=True)
    cache.put(_req("disk"), _resp("gone", "llama"))
    result = CliRunner().invoke(cli_app, ["cache", "invalidate", "--model", "llama"])
    assert result.exit_code == 0, result.stdout
    assert "L0: removed 1" in result.stdout
    assert cache.get(_req("disk")) is None


def _scoped_req(
    text: str,
    *,
    scope: str,
    team_id: str | None = None,
    key_id: str | None = None,
) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(cache_scope=scope, team_id=team_id, key_id=key_id),
    )


def test_exact_put_persists_scope_segment(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    cache.put(_scoped_req("a", scope="team", team_id="t1"), _resp("one", "llama"))
    cache.put(_scoped_req("b", scope="key", key_id="k1"), _resp("two", "llama"))
    cache.put(_req("c"), _resp("three", "llama"))
    store = cache._store()
    scopes = {
        cache._entry_scope(store.get(key))
        for key in store.iterkeys()
    }
    assert "team:t1" in scopes
    assert "key:k1" in scopes
    assert None in scopes  # global omits scope


def test_exact_invalidate_by_team_leaves_other_team(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    a = _scoped_req("a", scope="team", team_id="alpha")
    b = _scoped_req("b", scope="team", team_id="beta")
    cache.put(a, _resp("one", "llama"))
    cache.put(b, _resp("two", "llama"))
    assert cache.invalidate(team_id="gamma") == 0
    assert cache.get(a) is not None and cache.get(b) is not None
    assert cache.invalidate(team_id="alpha") == 1
    assert cache.get(a) is None
    assert cache.get(b) is not None


def test_exact_invalidate_by_key(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    a = _scoped_req("a", scope="key", key_id="k-a")
    b = _scoped_req("b", scope="key", key_id="k-b")
    cache.put(a, _resp("one", "llama"))
    cache.put(b, _resp("two", "llama"))
    assert cache.invalidate(key_id="k-a") == 1
    assert cache.get(a) is None
    assert cache.get(b) is not None


def test_redis_invalidate_by_team():
    client = _Redis()
    cache = RedisExactCache("redis://test", client=client, enabled=True)
    a = _scoped_req("a", scope="team", team_id="alpha")
    b = _scoped_req("b", scope="team", team_id="beta")
    cache.put(a, _resp("one", "llama"))
    cache.put(b, _resp("two", "llama"))
    assert cache.invalidate(team_id="alpha") == 1
    assert cache.get(a) is None
    assert cache.get(b) is not None


def test_semantic_invalidate_by_team_and_key(tmp_path):
    cache = SemanticCache(str(tmp_path / "l1"), _Embedder(), enabled=True)
    cache._save_entries(
        [
            {"context_key": "llama|0||team:alpha", "answer_hash": "aaa", "response_json": "{}"},
            {"context_key": "llama|0||team:beta", "answer_hash": "bbb", "response_json": "{}"},
            {"context_key": "llama|0||key:k1", "answer_hash": "ccc", "response_json": "{}"},
            {"context_key": "llama|0||", "answer_hash": "ddd", "response_json": "{}"},
        ]
    )
    assert cache.invalidate(team_id="alpha") == 1
    left = {row["answer_hash"] for row in cache._load_entries()}
    assert left == {"bbb", "ccc", "ddd"}
    assert cache.invalidate(key_id="k1") == 1
    left = {row["answer_hash"] for row in cache._load_entries()}
    assert left == {"bbb", "ddd"}


def test_cache_invalidate_cli_team(monkeypatch, settings, tmp_path):
    settings.cache.l0.path = str(tmp_path / "l0")
    settings.cache.l1.path = str(tmp_path / "l1")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr("daari.cli.app._daemon_is_running", lambda _settings: False)
    cache = ExactCache(str(settings.l0_cache_path), enabled=True)
    req = _scoped_req("disk", scope="team", team_id="ops")
    cache.put(req, _resp("gone", "llama"))
    result = CliRunner().invoke(cli_app, ["cache", "invalidate", "--team", "ops"])
    assert result.exit_code == 0, result.stdout
    assert "L0: removed 1" in result.stdout
    assert cache.get(req) is None


@pytest.mark.asyncio
async def test_admin_invalidate_by_team_id(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    req = _scoped_req("cached", scope="team", team_id="ops")
    app.state.ctx.router.cache.put(req, _resp("answer", "llama"))
    other = _scoped_req("keep", scope="team", team_id="other")
    app.state.ctx.router.cache.put(other, _resp("keep", "llama"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/cache/invalidate",
            json={"team_id": "ops"},
        )
    assert response.status_code == 200
    assert response.json()["l0_removed"] == 1
    assert app.state.ctx.router.cache.get(req) is None
    assert app.state.ctx.router.cache.get(other) is not None
