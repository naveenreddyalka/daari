"""Optional X-Daari-Priority request admission header (#2060)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daari.auth.virtual_keys import (
    VirtualKey,
    admission_priority_for,
    parse_priority_header,
    resolve_request_admission_priority,
)
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings: Settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.ollama.execute = fake
    return application


def test_parse_priority_header_valid_and_invalid() -> None:
    assert parse_priority_header(None) == (None, False)
    assert parse_priority_header("") == (None, False)
    assert parse_priority_header("  ") == (None, False)
    assert parse_priority_header("high") == ("high", False)
    assert parse_priority_header("NORMAL") == ("normal", False)
    assert parse_priority_header("Low") == ("low", False)
    assert parse_priority_header("urgent") == (None, True)
    assert parse_priority_header("1") == (None, True)


def test_resolve_lower_freely_and_boost_denied_by_default() -> None:
    key = VirtualKey(key_id="k1", name="ide", prefix="dk", priority="normal")
    assert admission_priority_for(key) == "normal"

    effective, warning, changed = resolve_request_admission_priority(
        key, header="low", allow_boost=False
    )
    assert effective == "low"
    assert warning is None
    assert changed is True

    effective, warning, changed = resolve_request_admission_priority(
        key, header="high", allow_boost=False
    )
    assert effective == "normal"
    assert warning is None
    assert changed is False


def test_resolve_boost_when_key_already_high_or_opt_in() -> None:
    high_key = VirtualKey(key_id="k2", name="ide", prefix="dk", priority="high")
    effective, warning, changed = resolve_request_admission_priority(
        high_key, header="high", allow_boost=False
    )
    assert effective == "high"
    assert warning is None
    assert changed is False

    normal_key = VirtualKey(key_id="k3", name="bot", prefix="dk", priority="normal")
    effective, warning, changed = resolve_request_admission_priority(
        normal_key, header="high", allow_boost=True
    )
    assert effective == "high"
    assert warning is None
    assert changed is True


def test_resolve_invalid_header_soft_warning_keeps_baseline() -> None:
    key = VirtualKey(key_id="k4", name="bot", prefix="dk", priority="low")
    effective, warning, changed = resolve_request_admission_priority(
        key, header="turbo", allow_boost=True
    )
    assert effective == "low"
    assert warning == "invalid_x_daari_priority"
    assert changed is False


def test_resolve_absent_header_unchanged() -> None:
    effective, warning, changed = resolve_request_admission_priority(
        None, header=None, allow_boost=False
    )
    assert effective == "normal"
    assert warning is None
    assert changed is False


@pytest.fixture
def priority_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    settings.rate_limit.max_in_flight = 4
    return settings


def _spy_acquire(app):
    limiter = app.state.rate_limiter
    calls: list[str] = []
    original = limiter.acquire

    async def wrapped(*, priority: str = "normal", **kwargs):
        calls.append(priority)
        return await original(priority=priority, **kwargs)

    limiter.acquire = wrapped  # type: ignore[method-assign]
    return calls


def test_gateway_header_lowers_priority(priority_settings, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload or {}))),
    )
    app = _app(priority_settings)
    calls = _spy_acquire(app)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer master",
            "X-Daari-Priority": "low",
        },
        json={
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert calls, f"acquire not called; status={r.status_code}"
    assert calls[0] == "low"
    assert any(e[0] == "admission_priority" for e in events)


def test_gateway_boost_denied_by_default_for_virtual_key(priority_settings, monkeypatch):
    from daari.auth.virtual_keys import VirtualKeyStore

    store = VirtualKeyStore(priority_settings.virtual_keys_path)
    created = store.create("ide", priority="normal")
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload or {}))),
    )
    app = _app(priority_settings)
    app.state.virtual_key_store = store
    calls = _spy_acquire(app)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {created.plaintext}",
            "X-Daari-Priority": "high",
        },
        json={
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert calls, f"acquire not called; status={r.status_code}"
    assert calls[0] == "normal"
    assert not any(e[0] == "admission_priority" for e in events)


def test_gateway_key_high_plus_header_high(priority_settings, monkeypatch):
    from daari.auth.virtual_keys import VirtualKeyStore

    store = VirtualKeyStore(priority_settings.virtual_keys_path)
    created = store.create("ide", priority="high")
    app = _app(priority_settings)
    app.state.virtual_key_store = store
    calls = _spy_acquire(app)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {created.plaintext}",
            "X-Daari-Priority": "high",
        },
        json={
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert calls, f"acquire not called; status={r.status_code}"
    assert calls[0] == "high"


def test_gateway_invalid_priority_warning_header(priority_settings, monkeypatch):
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda *_a, **_k: None,
    )
    app = _app(priority_settings)
    calls = _spy_acquire(app)
    client = TestClient(app)
    r = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer master",
            "X-Daari-Priority": "nope",
        },
        json={
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert calls and calls[0] == "normal"
    assert r.status_code == 200
    assert "invalid_x_daari_priority" in (r.headers.get("x-daari-warning") or "")


def test_docs_mention_x_daari_priority() -> None:
    root = Path(__file__).resolve().parents[2]
    headers = (root / "docs/developer/reference/headers.md").read_text(encoding="utf-8")
    auth = (root / "docs/developer/guides/configuration/auth-and-keys.md").read_text(
        encoding="utf-8"
    )
    assert "X-Daari-Priority" in headers
    assert "X-Daari-Priority" in auth or "allow_request_priority_boost" in auth
    assert "allow_request_priority_boost" in (
        root / "docs/developer/reference/config.md"
    ).read_text(encoding="utf-8")
