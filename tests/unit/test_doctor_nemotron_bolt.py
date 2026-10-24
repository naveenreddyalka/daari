"""Doctor tip for Nemotron Bolt E4B L3 VLM recipe (#1893)."""

from __future__ import annotations

from unittest.mock import MagicMock

from daari.setup.doctor import _ollama_nemotron_bolt_warning
from daari.setup.models import NEMOTRON_BOLT_MODEL


def test_bolt_warning_when_ollama_too_old(monkeypatch):
    monkeypatch.setattr(
        "daari.setup.doctor._ollama_version_payload",
        lambda http, base: ("0.40.9", (0, 40, 9)),
    )
    tip = _ollama_nemotron_bolt_warning(
        MagicMock(), "http://127.0.0.1:11434", NEMOTRON_BOLT_MODEL, l3_present=True
    )
    assert tip is not None
    assert tip.ok is False
    assert "0.40.10" in tip.detail


def test_bolt_warning_when_model_missing(monkeypatch):
    monkeypatch.setattr(
        "daari.setup.doctor._ollama_version_payload",
        lambda http, base: ("0.40.10", (0, 40, 10)),
    )
    tip = _ollama_nemotron_bolt_warning(
        MagicMock(), "http://127.0.0.1:11434", NEMOTRON_BOLT_MODEL, l3_present=False
    )
    assert tip is not None
    assert tip.ok is False
    assert "ollama pull" in tip.detail


def test_bolt_warning_absent_when_ready(monkeypatch):
    monkeypatch.setattr(
        "daari.setup.doctor._ollama_version_payload",
        lambda http, base: ("0.40.10", (0, 40, 10)),
    )
    tip = _ollama_nemotron_bolt_warning(
        MagicMock(), "http://127.0.0.1:11434", NEMOTRON_BOLT_MODEL, l3_present=True
    )
    assert tip is None


def test_bolt_warning_skips_other_l3(monkeypatch):
    tip = _ollama_nemotron_bolt_warning(
        MagicMock(), "http://127.0.0.1:11434", "llama3.2:3b", l3_present=False
    )
    assert tip is None
