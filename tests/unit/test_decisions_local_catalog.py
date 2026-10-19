"""Configurable local decisions catalog (#1590)."""

from __future__ import annotations

from pathlib import Path

import httpx

from daari.config.settings import Settings
from daari.gateway.decisions import (
    BUILTIN_LOCAL_MODELS,
    is_local_decisions_model,
    local_decisions_models,
    normalize_decisions_model,
)
from daari.setup.doctor import _check_decisions_local_models

ROOT = Path(__file__).resolve().parents[2]
OLLAMA_GUIDE = ROOT / "docs/developer/guides/backends/ollama.md"


def test_builtin_includes_drex_and_microsoft():
    assert "drex-1.5" in BUILTIN_LOCAL_MODELS
    assert "microsoft-decision-1" in BUILTIN_LOCAL_MODELS
    assert "nimble" in BUILTIN_LOCAL_MODELS


def test_normalize_accepts_new_ids_and_variants():
    assert normalize_decisions_model("drex-1.5") == "drex-1.5"
    assert normalize_decisions_model("nace/drex-1.5") == "drex-1.5"
    assert normalize_decisions_model("drex-1.5:latest") == "drex-1.5"
    assert normalize_decisions_model("microsoft-decision-1") == "microsoft-decision-1"
    assert normalize_decisions_model("microsoft/microsoft-decision-1") == "microsoft-decision-1"
    assert normalize_decisions_model("microsoft-decision-1:q4") == "microsoft-decision-1"
    assert normalize_decisions_model("gpt-4o") is None
    assert normalize_decisions_model("unknown-judge") is None


def test_settings_extension_round_trip():
    settings = Settings.model_validate(
        {"decisions": {"local_models": ["my-judge", "org/custom-decision"]}}
    )
    catalog = local_decisions_models(settings)
    assert "my-judge" in catalog
    assert "org/custom-decision" in catalog
    assert "nimble" in catalog
    assert is_local_decisions_model("my-judge", settings=settings)
    assert normalize_decisions_model("my-judge", settings=settings) == "my-judge"
    assert normalize_decisions_model("my-judge") is None  # without settings, builtin only
    assert not is_local_decisions_model("unknown-judge", settings=settings)


def test_doctor_tips_when_catalog_models_absent():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
            "decisions": {"local_models": ["drex-1.5"]},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = _check_decisions_local_models(settings, client)
    assert result is not None
    assert result.ok is False
    assert result.optional is True
    assert "drex-1.5" in result.detail or "nimble" in result.detail


def test_doctor_probes_explicit_systemone_models_not_ollama_tags():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True, "base_url": "http://vllm.test:8000"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "nimble:latest"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_decisions_local_models(settings, client) is None
    assert seen == ["http://vllm.test:8000/v1/models"]


def test_doctor_explicit_systemone_miss_names_that_base():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True, "base_url": "http://vllm.test:8000"},
            "ollama": {"base_url": "http://ollama.test"},
            "decisions": {"local_models": ["drex-1.5"]},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://vllm.test:8000/v1/models"
        return httpx.Response(200, json={"data": [{"id": "other-model"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = _check_decisions_local_models(settings, client)
    assert result is not None
    assert result.ok is False
    assert result.optional is True
    assert "http://vllm.test:8000" in result.detail
    assert "drex-1.5" in result.detail
    assert "ollama pull" not in result.detail
    assert "ollama.test" not in result.detail


def test_doctor_explicit_systemone_unreachable_is_quiet():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True, "base_url": "http://vllm.test:8000"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"models": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_decisions_local_models(settings, client) is None


def test_doctor_quiet_when_a_catalog_model_present():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "nimble:latest"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_decisions_local_models(settings, client) is None


def test_ollama_guide_documents_catalog_and_extension():
    text = OLLAMA_GUIDE.read_text(encoding="utf-8")
    assert "drex-1.5" in text
    assert "microsoft-decision-1" in text
    assert "decisions.local_models" in text
    assert "/v1/models" in text
    assert "/api/tags" in text
    assert "decision" in text
