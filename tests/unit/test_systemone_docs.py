"""Hermetic pin for systemone facade docs (#1314)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = ROOT / "docs/developer/guides/backends/ollama.md"
HTTP_API = ROOT / "docs/developer/reference/http-api.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_ollama_md_pins_systemone_facade() -> None:
    text = OLLAMA.read_text(encoding="utf-8")
    assert "POST /v1/systemone" in text
    assert "systemone.enabled" in text


def test_http_api_pins_systemone_row() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "| `POST` | `/v1/systemone`" in text
    assert "images" in text.lower()
    assert "systemone" in text.lower()


def test_ollama_md_pins_systemone_images() -> None:
    text = OLLAMA.read_text(encoding="utf-8")
    assert "images" in text
    assert "base64" in text.lower() or "Clef" in text or "clef" in text.lower()


def test_config_md_lists_systemone_enabled() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "systemone.enabled" in text
