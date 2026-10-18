"""GET /ready status contract is documented for operators (#1726)."""

from pathlib import Path


PAGE = Path("docs/developer/guides/operations/ready.md")
NAV = Path("mkdocs.yml")


def test_ready_page_lists_statuses_and_checks():
    text = PAGE.read_text(encoding="utf-8")
    for status in ("ready", "degraded", "not_ready", "shutting_down"):
        assert status in text
    assert "cache" in text
    assert "model_backend" in text
    assert "redis" in text
    assert "postgres" in text
    assert "/health" in text
    assert "liveness" in text
    nav = NAV.read_text(encoding="utf-8")
    assert "developer/guides/operations/ready.md" in nav
