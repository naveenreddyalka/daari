"""llama.cpp v0.8.0 local-tier guide + landscape refresh (#1998)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/developer/guides/configuration/llamacpp-local-tier.md"
LANDSCAPE = ROOT / "docs/discovery/04-competitive-landscape.md"
ASR = ROOT / "docs/developer/guides/backends/asr.md"
VLLM = ROOT / "docs/developer/guides/configuration/vllm-local-tier.md"


def test_llamacpp_guide_pins_v080_and_non_goals() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "v0.8.0" in text
    assert "github.com/ggml-org/llama.cpp/releases/tag/v0.8.0" in text
    assert "kind: openai" in text
    assert "llama-server" in text
    assert "LFM3" in text
    assert "d1" in text.lower() or "d1-2B" in text or "d1-omni" in text
    assert "0.40.12" in text
    assert "Apple" in text
    assert "/v1/realtime" in text
    assert "/tts" in text
    assert "systemone" in text.lower() or "decisions" in text.lower()
    assert "watch" in text.lower()


def test_landscape_has_dated_llamacpp_row() -> None:
    text = LANDSCAPE.read_text(encoding="utf-8")
    assert "llama.cpp v0.8.0" in text or "llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/v0.8.0)" in text
    assert "v0.8.0" in text
    assert "llamacpp-local-tier.md" in text
    assert "0.40.12" in text


def test_asr_and_vllm_cross_link_llamacpp_guide() -> None:
    assert "llamacpp-local-tier.md" in ASR.read_text(encoding="utf-8")
    assert "llamacpp-local-tier.md" in VLLM.read_text(encoding="utf-8")
