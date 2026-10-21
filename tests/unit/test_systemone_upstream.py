"""Configurable systemone upstream for OpenAI-compatible backends (#1778)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.ownership import live_config_payload, ownership_fields
from daari.gateway.decisions import evaluate_guardrail_predicate
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_decisions

ROOT = Path(__file__).resolve().parents[2]
CONFIG_MD = ROOT / "docs/developer/reference/config.md"


@pytest.fixture(autouse=True)
def _reset_systemone_breakers():
    from daari.gateway.systemone import reset_systemone_breakers

    reset_systemone_breakers()
    yield
    reset_systemone_breakers()

_SYSTEMONE_OK = {
    "model": "nimble",
    "answers": {
        "label": {
            "type": "choice",
            "choice": "bug",
            "probabilities": {"billing": 0.01, "bug": 0.98, "account": 0.01},
            "confidence": 0.9,
        }
    },
    "usage": {"input_tokens": 12, "output_tokens": 1},
}

_DECISIONS_BODY = {
    "model": "nimble",
    "input": "checkout returns 500",
    "questions": [
        {
            "type": "choice",
            "name": "label",
            "instructions": "Which label fits?",
            "choices": [
                {"value": "bug"},
                {"value": "billing"},
            ],
        }
    ],
}

_SYSTEMONE_BODY = {
    "model": "nimble",
    "state": "checkout returns 500",
    "questions": {
        "label": {
            "type": "choice",
            "instructions": "Which label fits?",
            "criteria": {"bug": "errors", "billing": "payments"},
        }
    },
}


def _patch_upstream(monkeypatch, handler):
    from daari.gateway import systemone

    systemone._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.systemone.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def test_systemone_base_url_defaults_empty(settings):
    assert settings.systemone.base_url == ""


def test_config_md_lists_systemone_base_url():
    text = CONFIG_MD.read_text(encoding="utf-8")
    assert "systemone.base_url" in text


def test_ownership_exposes_systemone_base_url(settings):
    settings.systemone.base_url = "http://vllm.local:8000"
    payload = live_config_payload(settings)
    assert payload["systemone"]["base_url"] == "http://vllm.local:8000"
    meta = ownership_fields(payload, file_doc={}, runtime_overrides=set())
    assert meta["systemone.base_url"]["editable"] is True


def test_patch_subset_accepts_systemone_base_url():
    from daari.config.validate import validated_systemone

    out = validated_systemone({"base_url": "http://vllm.local:8000/"})
    assert out["base_url"] == "http://vllm.local:8000"


@pytest.mark.asyncio
async def test_explicit_base_url_wins_over_ollama(settings, monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 200
    assert seen == ["http://vllm.local:8000/v1/systemone"]


@pytest.mark.asyncio
async def test_empty_both_bases_returns_existing_503(settings):
    settings.ollama.base_url = ""
    settings.systemone.base_url = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 503
    message = response.json()["error"]["message"]
    assert "Ollama" in message
    assert "ollama.base_url" in message


@pytest.mark.asyncio
async def test_override_503_names_configured_upstream(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = ""
    settings.systemone.base_url = "http://vllm.local:8000"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 503
    message = response.json()["error"]["message"]
    assert "http://vllm.local:8000" in message
    assert "require Ollama" not in message


@pytest.mark.asyncio
async def test_decisions_local_path_uses_override_url(settings, monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.decisions.cache_enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_DECISIONS_BODY)

    assert response.status_code == 200, response.text
    assert seen == ["http://vllm.local:8000/v1/systemone"]


def test_guardrail_predicate_uses_override_url(settings):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "answers": {
                    "guardrail": {"type": "boolean", "value": False, "probability": 0.1}
                }
            },
        )

    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    prob = evaluate_guardrail_predicate(
        text="hello",
        statement="Is this spam?",
        model="nimble",
        base_url=settings.ollama.base_url,
        client=client,
        settings=settings,
    )
    assert prob == pytest.approx(0.1)
    assert seen == ["http://vllm.local:8000/v1/systemone"]


def test_doctor_reports_ollama_default_upstream(settings):
    settings.systemone.enabled = True
    settings.systemone.base_url = ""
    settings.frontier.enabled = False
    detail = _check_decisions(settings).detail
    assert "ollama default" in detail


def _capture_events(monkeypatch) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.systemone.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    return events


@pytest.mark.asyncio
async def test_empty_base_keeps_ollama_meta(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    events = _capture_events(monkeypatch)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 200
    meta = response.json()["daari_meta"]
    assert meta["executor"] == "ollama"
    assert meta["provider_id"] == "ollama"
    ok = [payload for name, payload in events if name == "systemone_ok"]
    assert ok and ok[-1]["upstream"] == "ollama"


@pytest.mark.asyncio
async def test_explicit_base_labels_openai_compat_meta(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    events = _capture_events(monkeypatch)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 200
    meta = response.json()["daari_meta"]
    assert meta["executor"] == "openai-compat"
    assert meta["provider_id"] == "openai-compat"
    ok = [payload for name, payload in events if name == "systemone_ok"]
    assert ok and ok[-1]["upstream"] == "openai-compat"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [b"not-json", b"[]"],
)
async def test_explicit_base_bad_body_names_host_not_ollama(settings, monkeypatch, body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 502
    message = response.json()["error"]["message"]
    assert "Ollama" not in message
    assert "vllm.local" in message


@pytest.mark.asyncio
async def test_upstream_http_failure_records_request_id(settings, monkeypatch):
    # Non-retryable 4xx so the response reaches systemone_upstream_http (not retry).
    error_body = {"error": {"type": "upstream_error", "message": "boom"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json=error_body,
            headers={"x-request-id": "sys1_req_abc"},
        )

    _patch_upstream(monkeypatch, handler)
    events = _capture_events(monkeypatch)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 400
    assert response.json() == error_body
    failed = [payload for name, payload in events if name == "systemone_upstream_http"]
    assert len(failed) == 1
    assert failed[0]["status"] == 400
    assert failed[0]["upstream_request_id"] == "sys1_req_abc"


@pytest.mark.asyncio
async def test_upstream_http_failure_omits_id_when_headers_absent(settings, monkeypatch):
    error_body = {"error": {"type": "upstream_error", "message": "bad"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json=error_body)

    _patch_upstream(monkeypatch, handler)
    events = _capture_events(monkeypatch)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 422
    assert response.json() == error_body
    failed = [payload for name, payload in events if name == "systemone_upstream_http"]
    assert len(failed) == 1
    assert failed[0]["status"] == 422
    assert "upstream_request_id" not in failed[0]


def test_doctor_reports_explicit_base_url(settings):
    settings.systemone.enabled = True
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.frontier.enabled = False
    detail = _check_decisions(settings).detail
    assert "explicit base_url" in detail
    assert "http://vllm.local:8000" in detail


def test_systemone_api_key_defaults_empty(settings):
    assert settings.systemone.api_key == ""


def test_config_md_lists_systemone_api_key():
    text = CONFIG_MD.read_text(encoding="utf-8")
    assert "systemone.api_key" in text


def test_live_config_omits_systemone_api_key(settings):
    settings.systemone.api_key = "sk-systemone-secret"
    payload = live_config_payload(settings)
    assert "api_key" not in payload.get("systemone", {})
    dumped = str(payload)
    assert "sk-systemone-secret" not in dumped


@pytest.mark.asyncio
async def test_facade_sends_bearer_when_api_key_set(settings, monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.systemone.api_key = "sk-vllm-test"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 200
    assert seen == ["Bearer sk-vllm-test"]


@pytest.mark.asyncio
async def test_facade_omits_authorization_by_default(settings, monkeypatch):
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append("authorization" in request.headers)
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = ""
    settings.systemone.api_key = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)

    assert response.status_code == 200
    assert seen == [False]


@pytest.mark.asyncio
async def test_decisions_local_sends_bearer_when_api_key_set(settings, monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.systemone.api_key = "sk-decisions-key"
    settings.decisions.cache_enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_DECISIONS_BODY)

    assert response.status_code == 200, response.text
    assert seen == ["Bearer sk-decisions-key"]


def test_guardrail_predicate_sends_bearer_when_api_key_set(settings):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(
            200,
            json={
                "answers": {
                    "guardrail": {"type": "boolean", "value": False, "probability": 0.1}
                }
            },
        )

    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.systemone.api_key = "sk-guard-key"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    prob = evaluate_guardrail_predicate(
        text="hello",
        statement="Is this spam?",
        model="nimble",
        base_url=settings.ollama.base_url,
        client=client,
        settings=settings,
    )
    assert prob == pytest.approx(0.1)
    assert seen == ["Bearer sk-guard-key"]


def test_doctor_catalog_probe_sends_bearer_when_api_key_set(settings):
    from daari.setup.doctor import _check_decisions_local_models

    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"data": [{"id": "nimble"}]})

    settings.systemone.enabled = True
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.systemone.api_key = "sk-doctor-key"
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_decisions_local_models(settings, client) is None
    assert seen == ["Bearer sk-doctor-key"]


def test_redact_secrets_covers_resolved_systemone_api_key(settings, tmp_path):
    from daari.security.secret_refs import clear_registered_secrets, redact_secrets
    from daari.security.secret_refs import resolve_settings_secrets

    clear_registered_secrets()
    secret_file = tmp_path / "keys.env"
    secret_file.write_text("SYSTEMONE_KEY=sk-from-secret-ref\n", encoding="utf-8")
    settings.systemone.api_key = f"secret://env-file/{secret_file}#SYSTEMONE_KEY"
    resolve_settings_secrets(settings)
    assert settings.systemone.api_key == "sk-from-secret-ref"
    assert "[redacted]" in redact_secrets("upstream used sk-from-secret-ref")
    clear_registered_secrets()


@pytest.mark.asyncio
async def test_breaker_trips_then_fast_fails_with_retry_after(settings, monkeypatch):
    from daari.gateway.systemone import reset_systemone_breakers, breaker_for

    reset_systemone_breakers()
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        raise httpx.ConnectError("refused", request=request)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.upstream.retry.attempts = 1
    # Lower threshold so the test trips quickly.
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 2
    breaker.cooldown_seconds = 60.0
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            r = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)
            assert r.status_code == 503
        assert attempts["n"] == 2
        # Circuit open: no upstream attempt.
        r = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)
        assert r.status_code == 503
        assert attempts["n"] == 2
        assert "Retry-After" in r.headers
        assert r.json()["error"]["type"] == "backend_unavailable"


@pytest.mark.asyncio
async def test_breaker_recovers_after_cooldown(settings, monkeypatch):
    from daari.gateway.systemone import reset_systemone_breakers, breaker_for

    reset_systemone_breakers()
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.upstream.retry.attempts = 1
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 2
    breaker.cooldown_seconds = 0.0  # immediate half-open
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            assert (await client.post("/v1/systemone", json=_SYSTEMONE_BODY)).status_code == 503
        ok = await client.post("/v1/systemone", json=_SYSTEMONE_BODY)
        assert ok.status_code == 200
        assert attempts["n"] == 3


def test_breaker_prometheus_counter(settings, monkeypatch):
    from daari.gateway.systemone import reset_systemone_breakers, breaker_for, SystemOneCircuitOpen
    from daari.gateway.systemone import _reject_if_open, _note_failure
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    reset_systemone_breakers()
    metrics = Metrics()
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000", metrics=metrics)
    assert breaker.state == "open"
    try:
        _reject_if_open("http://vllm.local:8000", metrics=metrics)
        raise AssertionError("expected SystemOneCircuitOpen")
    except SystemOneCircuitOpen:
        pass
    text = render_prometheus(metrics)
    assert "daari_systemone_breaker_total" in text
    assert 'event="open"' in text or 'event="trip"' in text
    assert 'event="reject"' in text


def test_breaker_state_snapshot_gauge_stats_and_doctor(settings):
    """Trip → open → cooldown reset across snapshot/render/doctor (#1822)."""
    from daari.gateway.systemone import (
        SystemOneCircuitOpen,
        _note_failure,
        _note_success,
        _reject_if_open,
        breaker_for,
        breaker_snapshot,
        reset_systemone_breakers,
    )
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus
    from daari.setup.doctor import _check_systemone_breaker, run_doctor

    reset_systemone_breakers()
    base = "http://vllm.local:8000"
    metrics = Metrics()
    breaker = breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure(base, metrics=metrics)
    assert breaker.state == "open"
    try:
        _reject_if_open(base, metrics=metrics)
        raise AssertionError("expected SystemOneCircuitOpen")
    except SystemOneCircuitOpen:
        pass

    snap_rows = breaker_snapshot()
    assert len(snap_rows) == 1
    assert snap_rows[0]["base"] == "http://vllm.local:8000"
    assert snap_rows[0]["state"] == "open"
    assert snap_rows[0]["rejects"] == 1

    full = metrics.snapshot(include_histograms=True)
    assert full["systemone_breaker_state"][0]["state"] == "open"
    text = render_prometheus(metrics)
    assert "daari_systemone_breaker_state" in text
    assert 'base="http://vllm.local:8000"' in text
    assert 'state="open"' in text
    assert re.search(
        r'daari_systemone_breaker_state\{[^}]*base="http://vllm\.local:8000"[^}]*\} 1',
        text,
    )

    tip = _check_systemone_breaker(settings)
    assert tip is not None
    assert tip.ok is False
    assert "vllm.local:8000" in tip.detail
    assert "cooldown" in tip.detail
    doctor_rows = run_doctor(settings, httpx_client=None)
    assert any(r.name == "systemone_breaker" and not r.ok for r in doctor_rows)

    breaker.cooldown_seconds = 0.0
    _note_success(base)
    assert breaker.state == "closed"
    assert breaker_snapshot()[0]["state"] == "closed"
    assert _check_systemone_breaker(settings) is None
    closed_text = render_prometheus(metrics)
    assert 'state="closed"' in closed_text
    assert "daari_systemone_breaker_state" in closed_text


@pytest.mark.asyncio
async def test_stats_includes_systemone_breaker_state(settings, tmp_path):
    from httpx import ASGITransport, AsyncClient

    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers
    from daari.router.router import AppContext
    from daari.server.app import create_app

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/daari/stats",
            headers={"Authorization": "Bearer master-sekret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "systemone_breaker" in body
    assert body["systemone_breaker"][0]["state"] == "open"
    assert body["systemone_breaker"][0]["base"] == "http://vllm.local:8000"


def test_doctor_systemone_breaker_uses_daemon_stats(settings):
    """Doctor must report open circuits from the live daemon, not CLI process (#1842)."""
    from unittest.mock import MagicMock

    from daari.gateway.systemone import reset_systemone_breakers
    from daari.setup.doctor import _check_systemone_breaker

    reset_systemone_breakers()
    # In-process is closed/empty; daemon reports open.
    mock = MagicMock(spec=httpx.Client)
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "total_requests": 3,
        "systemone_breaker": [
            {
                "base": "http://vllm.local:8000",
                "state": "open",
                "rejects": 2,
                "cooldown_seconds": 30.0,
            }
        ],
    }
    mock.get.return_value = resp

    tip = _check_systemone_breaker(settings, httpx_client=mock)
    assert tip is not None
    assert tip.ok is False
    assert tip.name == "systemone_breaker"
    assert "vllm.local:8000" in tip.detail
    mock.get.assert_called()
    assert mock.get.call_args.args[0].endswith("/v1/daari/stats")


def test_doctor_systemone_breaker_falls_back_in_process(settings):
    from unittest.mock import MagicMock

    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers
    from daari.setup.doctor import _check_systemone_breaker

    reset_systemone_breakers()
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    _note_failure("http://vllm.local:8000")

    mock = MagicMock(spec=httpx.Client)
    mock.get.side_effect = httpx.ConnectError("refused")
    tip = _check_systemone_breaker(settings, httpx_client=mock)
    assert tip is not None
    assert tip.ok is False
    assert "vllm.local:8000" in tip.detail


@pytest.mark.asyncio
async def test_ready_includes_systemone_breaker_degraded_when_open(settings, monkeypatch):
    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers

    reset_systemone_breakers()
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["systemone_breaker"] == "open"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_ready_breaker_fails_ready_when_configured(settings, monkeypatch):
    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers

    reset_systemone_breakers()
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.systemone.breaker_fails_ready = True
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["checks"]["systemone_breaker"] == "open"
    assert body["status"] == "not_ready"


@pytest.mark.asyncio
async def test_admin_reset_systemone_breaker(settings, tmp_path):
    from daari.enterprise.audit import AuditLog
    from daari.gateway.systemone import (
        _note_failure,
        breaker_for,
        breaker_snapshot,
        reset_systemone_breakers,
    )

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")
    assert breaker_snapshot()[0]["state"] == "open"

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/daari/systemone/breaker/reset",
            headers={"Authorization": "Bearer master-sekret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert all(row["state"] == "closed" for row in body["systemone_breaker"])
    assert breaker_snapshot()[0]["state"] == "closed"
    rows = AuditLog(settings.enterprise.audit_path).list(action="systemone.breaker.reset")
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_reset_systemone_breaker_forbidden_for_non_admin(settings, tmp_path):
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.gateway.systemone import reset_systemone_breakers

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("viewer", client_id="viewer")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/daari/systemone/breaker/reset",
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert resp.status_code == 403


def test_doctor_health_docs_systemone_breaker_row():
    text = (ROOT / "docs/developer/guides/operations/doctor-health.md").read_text()
    assert "systemone_breaker" in text
