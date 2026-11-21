"""llama.cpp v1.0.0 local-tier guide + landscape / compare refresh (#2268)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/developer/guides/configuration/llamacpp-local-tier.md"
LANDSCAPE = ROOT / "docs/discovery/04-competitive-landscape.md"
COMPARE = ROOT / "docs/developer/resources/compare.md"
COMPARE_LITELLM = ROOT / "docs/developer/resources/compare-litellm.md"
TTS = ROOT / "docs/developer/guides/backends/tts.md"
OLLAMA_SETUP = ROOT / "docs/setup/ollama.md"
CAPACITY = ROOT / "docs/developer/guides/operations/capacity-helm.md"
ASR = ROOT / "docs/developer/guides/backends/asr.md"
VLLM = ROOT / "docs/developer/guides/configuration/vllm-local-tier.md"


def test_llamacpp_guide_pins_v100_security_tts_and_capacity() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "v1.0.0" in text
    assert "github.com/ggml-org/llama.cpp/releases/tag/v1.0.0" in text
    assert "kind: openai" in text
    assert "llama-server" in text
    assert "--allow-unauthenticated-tools" in text
    assert "--media-allow-private-urls" in text
    assert "HF_TOKEN" in text
    assert "/v1/audio/speech" in text
    assert "drama-3" in text
    assert "f8_e4m3" in text or "-ctk" in text
    assert "moe_cache" in text.lower() or "MoE" in text
    assert "Ripple" in text
    assert "/v1/realtime" in text
    assert "web UI" in text.lower() or "web ui" in text.lower()
    assert "LFM3" in text


def test_landscape_and_compare_pin_v100() -> None:
    landscape = LANDSCAPE.read_text(encoding="utf-8")
    assert "v1.0.0" in landscape
    assert "github.com/ggml-org/llama.cpp/releases/tag/v1.0.0" in landscape
    assert "llamacpp-local-tier.md" in landscape

    compare = COMPARE.read_text(encoding="utf-8")
    assert "v1.0.0" in compare
    assert "llamacpp-local-tier.md" in compare or "llama.cpp" in compare

    litellm = COMPARE_LITELLM.read_text(encoding="utf-8")
    assert "v1.0.0" in litellm or "llama.cpp" in litellm


def test_tts_ripple_capacity_cross_links() -> None:
    tts = TTS.read_text(encoding="utf-8")
    assert "llama-server" in tts or "llama.cpp" in tts
    assert "/v1/audio/speech" in tts
    assert "drama-3" in tts
    assert "response_format" in tts

    ollama = OLLAMA_SETUP.read_text(encoding="utf-8")
    assert "llamacpp-local-tier.md" in ollama
    assert "Ripple" in ollama

    capacity = CAPACITY.read_text(encoding="utf-8")
    assert "f8_e4m3" in capacity or "FP8" in capacity
    assert "MoE" in capacity or "moe_cache" in capacity.lower()


def test_asr_and_vllm_cross_link_llamacpp_guide() -> None:
    assert "llamacpp-local-tier.md" in ASR.read_text(encoding="utf-8")
    assert "llamacpp-local-tier.md" in VLLM.read_text(encoding="utf-8")
