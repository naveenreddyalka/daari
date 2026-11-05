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


def test_vllm_local_tier_guide_documents_033_upgrade_notes() -> None:
    """0.33.0 GA upgrade notes: CUDA 13-only, PyTorch 2.14, image alias, ROCm (#2087)."""
    text = GUIDE.read_text(encoding="utf-8")
    assert "0.33.0 upgrade notes" in text.lower() or "### 0.33.0 upgrade notes" in text.lower()
    assert "CUDA 13" in text or "CUDA 13.0" in text
    assert "cu129" in text
    assert "PyTorch 2.14" in text or "pytorch 2.14" in text.lower()
    assert "vllm/vllm" in text
    assert "ROCm 10" in text or "ROCm 10.0" in text
    # GitHub tag is v0.33.0rc3; release title is v0.33.0 (not marked prerelease).
    assert (
        "github.com/vllm-project/vllm/releases/tag/v0.33.0rc3" in text
        or "github.com/vllm-project/vllm/releases/tag/v0.33.0" in text
    )
