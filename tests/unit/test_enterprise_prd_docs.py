"""Hermetic pin: ENTERPRISE compact and MCP grant rows stay Shipped (#1370)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTERPRISE = ROOT / "docs/prd/ENTERPRISE.md"

# Gap-column cues for rows that must stay Shipped (prd-cycle must not restore
# "File this run" after compact ownership / MCP grant work landed).
_SHIPPED_GAP_CUES = (
    "Config ownership for `routing.compact_to_fit.*`",
    "Doctor tip when compact_to_fit is enabled",
    "Hermetic pin: compact_to_fit in config + routing-tiers",
    "`daari_meta` + stats when compact_to_fit actually trims",
    "Opt-in fail-closed MCP when key has no MCP grant",
)


def _gap_table_rows(text: str) -> list[str]:
    rows: list[str] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| # | Gap |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line.replace("|", "").strip()) <= {"-", ":"}:
                continue
            rows.append(line)
    return rows


def test_enterprise_prd_pins_compact_and_mcp_grant_rows_shipped() -> None:
    text = ENTERPRISE.read_text(encoding="utf-8")
    rows = _gap_table_rows(text)
    assert rows, "scored gap table missing from docs/prd/ENTERPRISE.md"
    for cue in _SHIPPED_GAP_CUES:
        matches = [row for row in rows if cue in row]
        assert matches, f"gap row not found for {cue!r}"
        for row in matches:
            assert "Shipped" in row, f"expected Shipped in gap row: {row}"
            assert "File this run" not in row, f"stale File this run in: {row}"
