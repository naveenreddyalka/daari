"""Chargeback guide names transcription and translation spend tiers (#756/#807)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/observability/chargeback.md"
CLI = ROOT / "docs/developer/reference/cli.md"


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


def test_chargeback_guide_documents_model_speed_and_http_export() -> None:
    """Chargeback guide names --model / --usage-speed and HTTP export (#1821)."""
    text = DOC.read_text(encoding="utf-8")
    assert "--model" in text
    assert "--usage-speed" in text
    assert "/v1/daari/spend/export" in text
    assert "usage_speed" in text


def test_chargeback_guide_documents_grouped_reports() -> None:
    """Chargeback guide names --group-by / --bucket and HTTP report (#1931)."""
    text = DOC.read_text(encoding="utf-8")
    assert "--group-by model,service_tier" in text
    assert "--bucket day" in text
    assert "hour" in text
    assert "/v1/daari/spend/report" in text
    assert "service_tier" in text


def test_chargeback_guide_names_tts_tier() -> None:
    text = DOC.read_text(encoding="utf-8")
    sentence = next(
        line for line in text.splitlines() if "Speech synthesis" in line and "`tts`" in line
    )
    assert "`tts`" in sentence
    assert "501" in text


def test_cli_reference_mentions_spend_export_tier() -> None:
    text = CLI.read_text(encoding="utf-8")
    spend_line = next(line for line in text.splitlines() if "`spend`" in line)
    assert "--tier" in spend_line


def test_cli_reference_mentions_spend_report_by_tool() -> None:
    """cli.md spend catalog row pins report --by-tool (#1245)."""
    text = CLI.read_text(encoding="utf-8")
    spend_line = next(line for line in text.splitlines() if "`spend`" in line)
    assert "report" in spend_line
    assert "--by-tool" in spend_line
    assert "--by-user" in spend_line
    assert "chargeback.md" in spend_line
