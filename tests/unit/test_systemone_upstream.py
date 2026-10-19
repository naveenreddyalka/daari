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


def test_doctor_reports_explicit_base_url(settings):
    settings.systemone.enabled = True
    settings.systemone.base_url = "http://vllm.local:8000"
    settings.frontier.enabled = False
    detail = _check_decisions(settings).detail
    assert "explicit base_url" in detail
    assert "http://vllm.local:8000" in detail
