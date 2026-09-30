"""mcp.md pins in-flight activity + force-abort (#1253)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_activity_and_force_abort() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "/v1/daari/mcp/activity" in text
    assert "/abort" in text
    assert "404" in text
    assert "mcp.activity.abort" in text
