"""ASR backend guide names the Helm base URL knob (#916)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASR_GUIDE = ROOT / "docs/developer/guides/backends/asr.md"


def test_asr_guide_names_helm_base_url() -> None:
    text = ASR_GUIDE.read_text(encoding="utf-8")
    assert "asr.baseUrl" in text
    assert "DAARI_ASR__BASE_URL" in text


def test_asr_guide_names_helm_model() -> None:
    text = ASR_GUIDE.read_text(encoding="utf-8")
    assert "asr.model" in text
    assert "DAARI_ASR__MODEL" in text
