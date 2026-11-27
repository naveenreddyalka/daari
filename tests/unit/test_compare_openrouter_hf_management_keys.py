"""Hermetic pin: OpenRouter HF Inference Providers + scoped management keys (#2339)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "docs/developer/resources/compare-openrouter.md"
INDEX = ROOT / "docs/developer/resources/compare.md"
TRACKING = ROOT / "docs/TRACKING.md"


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    assert start >= 0, heading
    nxt = text.find("\n## ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def test_compare_openrouter_pins_hf_inference_providers() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    section = _section(text, "## Hugging Face Inference Providers")
    lower = section.lower()
    assert "openrouter.ai/blog/announcements/hugging-face-inference-providers" in section
    assert "2026-11-16" in section or "16 nov 2026" in lower
    assert "X-HF-Session-Id" in section
    assert "session_affinity" in section or "X-Daari-Session" in section
    assert "base_url" in section
    assert "l6" in lower
    assert "local tier" in lower
    assert "unchanged" in lower
    # Existing pin behavior, not a new HF feature and not a native broker.
    assert "does not broker" in lower or "does **not** broker" in lower
    assert "not a new feature" in lower or "existing pin" in lower or "already" in lower
    assert "natively" in lower


def test_compare_openrouter_pins_scoped_management_keys() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    section = _section(text, "## Scoped management keys")
    lower = section.lower()
    assert "openrouter.ai/blog/announcements/scoped-management-keys" in section
    assert "read-only" in lower or "read only" in lower
    assert "workspace" in lower
    assert "virtual key" in lower or "virtual-keys" in lower
    assert "byok" in lower
    assert "grant" in lower
    assert "does not clone" in lower or "does **not** clone" in lower
    # Control-plane strength on OpenRouter; on-box keys are the counterpart.
    assert "control-plane" in lower or "control plane" in lower


def test_compare_index_mentions_nov_2026_openrouter_deltas() -> None:
    text = INDEX.read_text(encoding="utf-8")
    lower = text.lower()
    assert "compare-openrouter.md" in text
    assert "inference providers" in lower or "hugging face" in lower
    assert "management key" in lower


def test_tracking_records_2339() -> None:
    text = TRACKING.read_text(encoding="utf-8")
    assert "<!-- tracking:#2339 -->" in text
    assert "#2339" in text
