"""Doctor tip when routing.decision_classifier.enabled (#1313)."""

from __future__ import annotations

from daari.setup.doctor import _check_decision_classifier, run_doctor


def test_tip_when_decision_classifier_enabled(settings):
    settings.routing.decision_classifier.enabled = True
    row = _check_decision_classifier(settings)
    assert row is not None
    assert row.name == "decision_classifier"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "systemone" in detail or "difficulty" in detail or "classifier" in detail
    assert "heuristic" in detail or "fallback" in detail


def test_tip_absent_when_decision_classifier_disabled(settings):
    settings.routing.decision_classifier.enabled = False
    assert _check_decision_classifier(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "decision_classifier" for r in rows)


def test_doctor_health_docs_mention_decision_classifier_tip():
    from pathlib import Path

    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "decision_classifier" in text
    assert "systemone" in text.lower() or "difficulty" in text.lower()
