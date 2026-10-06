"""Hermetic pin: compare-litellm notes LiteLLM 1.104 GA parity (#1393, #1420)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/resources/compare-litellm.md"
)


def test_compare_litellm_pins_1104_ga_parity() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "1.104" in text
    lower = text.lower()
    assert "master" in lower and "key" in lower
    assert "compact-to-fit" in lower or "compact_to_fit" in lower
    assert "mcp" in lower and ("grant" in lower or "fail-closed" in lower)
    assert "stdio" in lower
    assert "docs.litellm.ai" in text or "litellm.ai/release" in text


def test_compare_litellm_pins_compact_to_fit_token_telemetry() -> None:
    """Buyers comparing FinOps compact telemetry see on-device fields (#1420)."""
    text = DOC.read_text(encoding="utf-8")
    lower = text.lower()
    assert "compact-to-fit" in lower or "compact_to_fit" in lower
    assert "tokens_before" in text
    assert "tokens_after" in text
    assert (
        "compact_to_fit_tokens_dropped" in text or "tokens dropped" in lower
    )


def test_compare_litellm_pins_1105_rc_watch() -> None:
    text = DOC.read_text(encoding="utf-8")
    lower = text.lower()
    assert "1.105" in text
    assert "rc" in lower or "prerelease" in lower
    assert "1.104" in text
    assert "microsoft 365" in lower or "m365" in lower
    assert "mcp" in lower
    assert "straiker" in lower
    assert "lens" in lower or "litellm.agent" in lower
    assert "does **not** ship" in lower or "does not ship" in lower
    assert "watch" in lower
