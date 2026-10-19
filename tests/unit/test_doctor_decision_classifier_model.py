"""Doctor tip when decision_classifier model missing from Ollama tags (#1321)."""

from __future__ import annotations

from pathlib import Path

import httpx

from daari.setup.doctor import _check_decision_classifier_model, run_doctor


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tip_when_model_missing(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    row = _check_decision_classifier_model(settings, _client(handler))
    assert row is not None
    assert row.name == "decision_classifier_model"
    assert row.optional is True
    assert row.ok is False
    detail = row.detail.lower()
    assert "nimble" in detail
    assert "ollama pull" in detail


def test_quiet_when_model_present_with_tag(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "nimble:latest"}]})

    assert _check_decision_classifier_model(settings, _client(handler)) is None


def test_explicit_systemone_base_probes_models_not_ollama_tags(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"
    settings.systemone.base_url = "http://vllm.test:8000"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"data": [{"id": "nimble:latest"}]})

    assert _check_decision_classifier_model(settings, _client(handler)) is None
    assert seen == ["http://vllm.test:8000/v1/models"]


def test_explicit_systemone_miss_does_not_say_ollama_pull(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"
    settings.systemone.base_url = "http://vllm.test:8000"
    settings.ollama.base_url = "http://ollama.test"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://vllm.test:8000/v1/models"
        return httpx.Response(200, json={"data": [{"id": "other"}]})

    row = _check_decision_classifier_model(settings, _client(handler))
    assert row is not None
    assert row.ok is False
    assert "http://vllm.test:8000" in row.detail
    assert "nimble" in row.detail
    assert "ollama pull" not in row.detail
    assert "ollama.test" not in row.detail


def test_explicit_systemone_unreachable_is_quiet(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"
    settings.systemone.base_url = "http://vllm.test:8000"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"models": []})

    assert _check_decision_classifier_model(settings, _client(handler)) is None


def test_quiet_when_classifier_disabled(settings):
    settings.routing.decision_classifier.enabled = False

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not call Ollama when disabled")

    assert _check_decision_classifier_model(settings, _client(handler)) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "decision_classifier_model" for r in rows)


def test_quiet_when_ollama_unreachable(settings):
    settings.routing.decision_classifier.enabled = True
    settings.routing.decision_classifier.model = "nimble"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    assert _check_decision_classifier_model(settings, _client(handler)) is None


def test_doctor_health_docs_mention_model_tip():
    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "decision_classifier_model" in text
    assert "ollama pull" in text.lower()
