"""Doctor-health documents mcp_oauth_local_as tip (#1323)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_mcp_oauth_local_as_row() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("| doctor `mcp_oauth_local_as`")
    )
    assert "mcp_oauth.local_as" in row
    assert "/oauth/token" in row
