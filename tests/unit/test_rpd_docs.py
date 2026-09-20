"""Key guides mention the per-key/per-team daily request cap (#733)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_virtual_keys_and_config_mention_rpd() -> None:
    virtual_keys = (ROOT / "docs/developer/guides/features/virtual-keys.md").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "--rpd" in virtual_keys
    assert "unlimited" in virtual_keys
    assert "rpd" in config
    assert "auth-and-keys.md" in config
    assert "rate_limit" in config
