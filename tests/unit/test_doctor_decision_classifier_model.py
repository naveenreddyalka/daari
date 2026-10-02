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
