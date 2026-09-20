"""Chargeback guide names transcription and translation spend tiers (#756/#807)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/guides/observability/chargeback.md"
)


def test_chargeback_guide_names_transcription_tiers() -> None:
    text = DOC.read_text(encoding="utf-8")
    sentence = next(
        line for line in text.splitlines() if "transcription" in line and "tier" in line
    )
    assert "`asr`" in sentence
    assert "`L6`" in sentence
    assert "403" in sentence
    assert "501" in sentence


def test_chargeback_guide_names_translation_tier() -> None:
    text = DOC.read_text(encoding="utf-8")
    sentence = next(
        line for line in text.splitlines() if "translation" in line and "`translation`" in line
    )
    assert "`translation`" in sentence
    assert "`L6`" in sentence


def test_chargeback_guide_documents_tier_filter() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "--tier asr" in text
    assert "--tier tts" in text
    assert "--tier embed" in text
    assert "`asr`" in text and "`translation`" in text and "`tts`" in text and "`embed`" in text


def test_chargeback_guide_names_tts_tier() -> None:
    text = DOC.read_text(encoding="utf-8")
    sentence = next(
        line for line in text.splitlines() if "Speech synthesis" in line and "`tts`" in line
    )
    assert "`tts`" in sentence
    assert "501" in text
