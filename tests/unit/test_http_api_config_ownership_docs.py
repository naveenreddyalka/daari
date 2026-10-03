"""http-api.md pin for /v1/daari/config ownership classifier and MCP knobs (#1338)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_http_api_pins_config_ownership_classifier_and_mcp_knobs() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/daari/config" in text
    assert "decision_classifier" in text
    mcp_cues = ("mcp_oauth.local_as", "mcp_aggregate_egress", "mcp_registry")
    assert sum(1 for cue in mcp_cues if cue in text) >= 2
    assert "compact_to_fit" in text
