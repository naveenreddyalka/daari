"""vLLM local-tier guide pins a security floor (#1873)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/developer/guides/configuration/vllm-local-tier.md"
CONFIG_REF = ROOT / "docs/developer/reference/config.md"


def test_vllm_local_tier_guide_pins_security_floor() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "≥0.32.0" in text or ">=0.32.0" in text
    assert "0.32.0" in text
    assert "github.com/vllm-project/vllm/releases/tag/v0.32.0" in text
    assert "security" in text.lower()


def test_vllm_local_tier_guide_aligns_with_systemone_config_ref() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    config = CONFIG_REF.read_text(encoding="utf-8")
    assert "0.32" in config
    assert "systemone" in guide.lower()
    assert "config.md" in guide or "reference/config" in guide
