"""Docs contract: fleet Responses background cancel (#1874)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_batches_guide_documents_fleet_background_cancel():
    text = (ROOT / "docs/developer/guides/features/batches.md").read_text(encoding="utf-8")
    compact = " ".join(text.split())
    assert "Background Responses cancel across replicas" in text
    assert "cache.backend: redis" in compact
    assert "shared cancel flag" in compact


def test_clients_guide_links_fleet_cancel():
    text = (ROOT / "docs/developer/concepts/clients-and-gateways.md").read_text(encoding="utf-8")
    assert "cache.backend: redis" in text
    assert "batches.md#background-responses-cancel-across-replicas" in text
