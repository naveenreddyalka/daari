"""Doctor tips when Ollama serves d1 / lfm3 but daari leaves them unused (#1985)."""

from __future__ import annotations

import httpx

from daari.config.settings import Settings
from daari.setup.doctor import (
    _check_decisions_unused_host_models,
    _check_lfm3_unused,
)
from daari.setup.models import LFM3_MODEL


def _tags_client(names: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(
                200, json={"models": [{"name": n} for n in names]}
            )
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(
                200, json={"data": [{"id": n} for n in names]}
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_decisions_tip_when_host_has_d1_not_in_catalog(monkeypatch):
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    monkeypatch.setattr(
        "daari.gateway.decisions.local_decisions_models",
        lambda _settings: frozenset({"nimble", "clef"}),
    )
    tip = _check_decisions_unused_host_models(
        settings, _tags_client(["d1:2b", "llama3.2:3b"])
    )
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "decisions_unused_host_models"
    assert "d1:2b" in tip.detail
    assert "decisions.local_models" in tip.detail


def test_decisions_tip_quiet_when_d1_already_in_catalog():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_decisions_unused_host_models(
        settings, _tags_client(["d1:2b", "d1-omni"])
    )
    assert tip is None


def test_decisions_tip_quiet_when_systemone_off():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": False},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_decisions_unused_host_models(
        settings, _tags_client(["d1:2b"])
    )
    assert tip is None


def test_decisions_tip_quiet_when_ollama_unreachable():
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_decisions_unused_host_models(settings, client) is None


def test_decisions_tip_probes_explicit_systemone_v1_models(monkeypatch):
    settings = Settings.model_validate(
        {
            "systemone": {"enabled": True, "base_url": "http://vllm.test:8000"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    monkeypatch.setattr(
        "daari.gateway.decisions.local_decisions_models",
        lambda _settings: frozenset({"nimble"}),
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "d1"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    tip = _check_decisions_unused_host_models(settings, client)
    assert tip is not None
    assert "d1" in tip.detail
    assert seen == ["http://vllm.test:8000/v1/models"]


def test_lfm3_tip_when_host_has_lfm3_but_l3_elsewhere():
    settings = Settings.model_validate(
        {
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    tip = _check_lfm3_unused(settings, _tags_client([LFM3_MODEL, "llama3.2:3b"]))
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_lfm3_unused"
    assert LFM3_MODEL in tip.detail
    assert "daari setup models" in tip.detail


def test_lfm3_tip_quiet_when_l3_already_lfm3():
    settings = Settings.model_validate(
        {
            "models": {"l3": LFM3_MODEL},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_lfm3_unused(settings, _tags_client([LFM3_MODEL])) is None


def test_lfm3_tip_quiet_when_lfm3_absent_on_host():
    settings = Settings.model_validate(
        {
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_lfm3_unused(settings, _tags_client(["llama3.2:3b"])) is None


def test_lfm3_tip_quiet_when_ollama_unreachable():
    settings = Settings.model_validate(
        {
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert _check_lfm3_unused(settings, client) is None
