"""Virtual-keys guide documents admission --priority (#877)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_virtual_keys_guide_documents_priority() -> None:
    text = (ROOT / "docs/developer/guides/features/virtual-keys.md").read_text(
        encoding="utf-8"
    )
    assert "--priority" in text
    assert "high" in text and "low" in text
    assert "Admission priority" in text


def test_virtual_keys_guide_documents_models_allowlist_filter() -> None:
    """Filtered GET /v1/models catalog stays documented (#1585)."""
    text = (ROOT / "docs/developer/guides/features/virtual-keys.md").read_text(
        encoding="utf-8"
    )
    assert "GET /v1/models" in text
    assert "allowlist" in text.lower() or "allowed_models" in text
    assert "Model allowlists" in text
