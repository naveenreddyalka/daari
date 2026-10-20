"""Configurable systemone upstream for OpenAI-compatible backends (#1778)."""

from __future__ import annotations

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
