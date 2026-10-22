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


@pytest.mark.asyncio
async def test_admin_invalidate_writes_audit_row(settings, tmp_path, monkeypatch):
    """Successful admin invalidate writes cache.invalidate audit (#1657)."""
    from daari.enterprise.audit import AuditLog

    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.cache.put(_req("cached"), _resp("answer", "llama"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/cache/invalidate",
            json={"model": "llama"},
            headers={"x-daari-actor": "ops-alice"},
        )
    assert response.status_code == 200
    body = response.json()
    rows = AuditLog(settings.enterprise.audit_path).list(action="cache.invalidate")
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "ops-alice"
    assert row["role"] == "admin"
    detail = row["detail"]
    assert detail["scope"] == "model"
    assert detail["l0_removed"] == body["l0_removed"]
    assert detail["l1_removed"] == body["l1_removed"]
    assert "Authorization" not in str(detail)
    assert "sk-" not in str(detail)


@pytest.mark.asyncio
async def test_admin_invalidate_error_skips_success_audit(settings, tmp_path):
    """Invalidate failure bumps Prom error and does not write success audit (#1657)."""
    from daari.enterprise.audit import AuditLog
    from daari.observability.prometheus import render_prometheus

    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    class _Boom:
        def invalidate(self, **_kwargs):
            raise RuntimeError("boom")

    app.state.ctx.router.cache = _Boom()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(RuntimeError, match="boom"):
            await client.post("/v1/daari/cache/invalidate", json={"model": "llama"})
    rows = AuditLog(settings.enterprise.audit_path).list(action="cache.invalidate")
    assert rows == []
    text = render_prometheus(app.state.ctx.metrics)
    assert 'daari_cache_invalidate_total{scope="model",result="error"}' in text


def test_auth_guide_lists_cache_invalidate_audit():
    text = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs/developer/guides/configuration/auth-and-keys.md"
    ).read_text(encoding="utf-8")
    assert "`cache.invalidate`" in text
    assert "/v1/daari/cache/invalidate" in text


def test_cache_prune_notes_redis_ttl(monkeypatch, settings):
    settings.cache.backend = "redis"
    settings.cache.l0.ttl_seconds = 120
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    class _NoScan:
        def prune(self) -> int:
            return 0

    monkeypatch.setattr("daari.router.router._build_l0_cache", lambda *_a, **_k: _NoScan())
    result = CliRunner().invoke(cli_app, ["cache", "prune"])
    assert result.exit_code == 0
    assert "Redis relies on TTL" in result.stdout
    assert "does not scan" in result.stdout


def test_cache_prune_redis_unbounded_reports_count(monkeypatch, settings):
    settings.cache.backend = "redis"
    settings.cache.l0.ttl_seconds = 0
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

    class _Pruned:
        def prune(self) -> int:
            return 3

    monkeypatch.setattr("daari.router.router._build_l0_cache", lambda *_a, **_k: _Pruned())
    result = CliRunner().invoke(cli_app, ["cache", "prune"])
    assert result.exit_code == 0, result.stdout
    assert "L0: removed 3" in result.stdout
    assert "older than 7d" in result.stdout


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


@pytest.mark.asyncio
async def test_sso_invalidate_requires_bearer_master_key(settings):
    """SSO-on admin invalidate: 401 without Bearer, 200 with master key (#816)."""
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-dev-secret"
    settings.server.api_key = "master-secret"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.cache.put(_req("cached"), _resp("answer", "llama"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/v1/daari/cache/invalidate", json={"model": "llama"})
        assert denied.status_code == 401
        denied_text = denied.text.lower()
        assert "token" in denied_text or "api key" in denied_text or "sso" in denied_text

        ok = await client.post(
            "/v1/daari/cache/invalidate",
            json={"model": "llama"},
            headers={"Authorization": "Bearer master-secret"},
        )
    assert ok.status_code == 200
    assert ok.json()["l0_removed"] == 1
    assert app.state.ctx.router.cache.get(_req("cached")) is None


def test_daemon_invalidate_sends_bearer_under_sso(monkeypatch, settings):
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-dev-secret"
    settings.server.api_key = "master-secret"
    seen: dict[str, object] = {}

    def fake_post(url, json=None, headers=None, timeout=5.0):
        seen["url"] = url
        seen["headers"] = headers or {}
        seen["json"] = json

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"removed": 2, "l0_removed": 1, "l1_removed": 1}

        return Resp()

    monkeypatch.setattr("daari.cli.app.httpx.post", fake_post)
    from daari.cli.app import _daemon_invalidate_caches

    ok, detail = _daemon_invalidate_caches(settings, model="llama", entry_hash=None)
    assert ok is True
    assert seen["headers"].get("Authorization") == "Bearer master-secret"
    assert "Invalidated 2" in detail


def test_daemon_invalidate_sso_without_token_is_clear(settings):
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-dev-secret"
    settings.server.api_key = ""
    from daari.cli.app import _daemon_invalidate_caches

    ok, detail = _daemon_invalidate_caches(settings, model="llama", entry_hash=None)
    assert ok is False
    assert "SSO token required" in detail


def _speed_req(text: str, *, speed: str | None, model: str = "daari") -> InternalRequest:
    from daari.gateway.sampling import SamplingParams

    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model=model,
        sampling=SamplingParams(speed=speed),
    )


def test_exact_invalidate_by_speed_leaves_other_mode(tmp_path):
    """speed=fast drops only fast-fingerprint L0 rows; standard stays (#1826)."""
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    fast = _speed_req("same", speed="fast")
    standard = _speed_req("same", speed="standard")
    plain = _speed_req("same", speed=None)
    cache.put(fast, _resp("fast-ans", "claude"))
    cache.put(standard, _resp("std-ans", "claude"))
    cache.put(plain, _resp("plain-ans", "claude"))
    assert cache.invalidate(speed="fast") == 1
    assert cache.get(fast) is None
    assert cache.get(standard) is not None
    assert cache.get(plain) is not None
    assert cache.invalidate(model="claude") == 2
    assert cache.get(standard) is None
    assert cache.get(plain) is None


def test_redis_invalidate_by_speed():
    client = _Redis()
    cache = RedisExactCache("redis://test", client=client, enabled=True)
    fast = _speed_req("a", speed="fast")
    standard = _speed_req("a", speed="standard")
    cache.put(fast, _resp("one", "claude"))
    cache.put(standard, _resp("two", "claude"))
    assert cache.invalidate(speed="fast") == 1
    assert cache.get(fast) is None
    assert cache.get(standard) is not None


def test_semantic_invalidate_by_speed(tmp_path):
    cache = SemanticCache(str(tmp_path / "l1"), _Embedder(), enabled=True)
    cache._save_entries(
        [
            {
                "context_key": "claude|0|||speed:fast",
                "answer_hash": "aaa",
                "response_json": "{}",
            },
            {
                "context_key": "claude|0|||speed:standard",
                "answer_hash": "bbb",
                "response_json": "{}",
            },
            {"context_key": "claude|0||", "answer_hash": "ccc", "response_json": "{}"},
        ]
    )
    assert cache.invalidate(speed="fast") == 1
    left = {row["answer_hash"] for row in cache._load_entries()}
    assert left == {"bbb", "ccc"}
    assert cache.invalidate(model="claude") == 2
    assert cache._load_entries() == []


def test_cache_invalidate_cli_speed(monkeypatch, settings, tmp_path):
    settings.cache.l0.path = str(tmp_path / "l0")
    settings.cache.l1.path = str(tmp_path / "l1")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr("daari.cli.app._daemon_is_running", lambda _settings: False)
    cache = ExactCache(str(settings.l0_cache_path), enabled=True)
    fast = _speed_req("disk", speed="fast")
    standard = _speed_req("disk", speed="standard")
    cache.put(fast, _resp("gone", "claude"))
    cache.put(standard, _resp("keep", "claude"))
    result = CliRunner().invoke(cli_app, ["cache", "invalidate", "--speed", "fast"])
    assert result.exit_code == 0, result.stdout
    assert "L0: removed 1" in result.stdout
    assert cache.get(fast) is None
    assert cache.get(standard) is not None


@pytest.mark.asyncio
async def test_admin_invalidate_by_speed(settings, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.openai.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    fast = _speed_req("cached", speed="fast")
    standard = _speed_req("cached", speed="standard")
    app.state.ctx.router.cache.put(fast, _resp("answer", "claude"))
    app.state.ctx.router.cache.put(standard, _resp("keep", "claude"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/cache/invalidate",
            json={"speed": "fast"},
        )
    assert response.status_code == 200
    assert response.json()["l0_removed"] == 1
    assert app.state.ctx.router.cache.get(fast) is None
    assert app.state.ctx.router.cache.get(standard) is not None
    assert events and events[-1][0] == "cache_invalidate"
    assert events[-1][1].get("speed") == "fast"


def test_daemon_invalidate_forwards_speed(monkeypatch, settings):
    seen: dict[str, object] = {}

    def fake_post(url, json=None, headers=None, timeout=5.0):
        seen["json"] = json

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"removed": 1, "l0_removed": 1, "l1_removed": 0}

        return Resp()

    monkeypatch.setattr("daari.cli.app.httpx.post", fake_post)
    from daari.cli.app import _daemon_invalidate_caches

    ok, detail = _daemon_invalidate_caches(
        settings, model=None, entry_hash=None, speed="fast"
    )
    assert ok is True
    assert seen["json"] == {"speed": "fast"}
    assert "Invalidated 1" in detail


@pytest.mark.asyncio
async def test_team_pinned_admin_invalidate_auto_scopes_empty_body(settings, tmp_path):
    """SSO admin with team_id=eng + {} body clears only eng rows (#1845)."""
    from daari.enterprise.sso import mint_dev_token

    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-hs-secret"
    settings.enterprise.sso.issuer = "daari-dev"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    eng = _scoped_req("eng-row", scope="team", team_id="eng")
    ops = _scoped_req("ops-row", scope="team", team_id="ops")
    app.state.ctx.router.cache.put(eng, _resp("e", "llama"))
    app.state.ctx.router.cache.put(ops, _resp("o", "llama"))
    token = mint_dev_token(
        subject="lead",
        role="admin",
        secret="sso-hs-secret",
        issuer="daari-dev",
        extra={"team_id": "eng"},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/daari/cache/invalidate",
            json={"team_id": "ops"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 403

        ok = await client.post(
            "/v1/daari/cache/invalidate",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert ok.status_code == 200
    assert ok.json()["l0_removed"] == 1
    assert app.state.ctx.router.cache.get(eng) is None
    assert app.state.ctx.router.cache.get(ops) is not None


def test_offline_cli_invalidate_writes_audit_row(monkeypatch, settings, tmp_path):
    """Offline CLI invalidate records cache.invalidate with offline: true (#1845)."""
    from daari.enterprise.audit import AuditLog

    settings.cache.l0.path = str(tmp_path / "l0")
    settings.cache.l1.path = str(tmp_path / "l1")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr("daari.cli.app._daemon_is_running", lambda _settings: False)
    cache = ExactCache(str(settings.l0_cache_path), enabled=True)
    req = _scoped_req("disk", scope="team", team_id="ops")
    cache.put(req, _resp("gone", "llama"))
    result = CliRunner().invoke(cli_app, ["cache", "invalidate", "--team", "ops"])
    assert result.exit_code == 0, result.stdout
    rows = AuditLog(settings.enterprise.audit_path).list(action="cache.invalidate")
    assert len(rows) == 1
    detail = rows[0]["detail"]
    assert detail["offline"] is True
    assert detail["team_id"] == "ops"
    assert detail["l0_removed"] == 1
    assert detail["scope"] == "team"


def test_org_cache_doc_mentions_team_pin_scope():
    text = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "docs/developer/guides/features/org-cache.md"
    ).read_text(encoding="utf-8")
    assert "team-pinned" in text.lower() or "team_id claim" in text
    assert "403" in text
    assert "offline: true" in text
