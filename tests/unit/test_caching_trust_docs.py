"""caching-and-trust docs mention agent-prefix multimodal fold (#1043)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/concepts/caching-and-trust.md"


def test_caching_trust_docs_mention_agent_prefix_multimodal() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "agent_prefix_text" in text
    assert "_message_embed_chunk" in text
    assert "ContentAudio.cache_token()" in text
    assert "ContentImage.cache_token()" in text
