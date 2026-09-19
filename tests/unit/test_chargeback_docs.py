"""Chargeback guide names transcription spend tiers (#756)."""

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
