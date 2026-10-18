"""Hermetic pin: compare-litellm notes LiteLLM 1.104 GA parity (#1393, #1420)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/resources/compare-litellm.md"
)


def test_compare_litellm_pins_1104_ga_parity() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "1.104" in text
    lower = text.lower()
    assert "master" in lower and "key" in lower
    assert "compact-to-fit" in lower or "compact_to_fit" in lower
    assert "mcp" in lower and ("grant" in lower or "fail-closed" in lower)
    assert "stdio" in lower
    assert "docs.litellm.ai" in text or "litellm.ai/release" in text


def test_compare_litellm_pins_compact_to_fit_token_telemetry() -> None:
    """Buyers comparing FinOps compact telemetry see on-device fields (#1420)."""
    text = DOC.read_text(encoding="utf-8")
    lower = text.lower()
    assert "compact-to-fit" in lower or "compact_to_fit" in lower
    assert "tokens_before" in text
    assert "tokens_after" in text
    assert (
        "compact_to_fit_tokens_dropped" in text or "tokens dropped" in lower
    )


def _markdown_section(text: str, heading_prefix: str) -> str:
    start = text.find(heading_prefix)
    assert start >= 0, heading_prefix
    rest = text[start + len(heading_prefix) :]
    nxt = rest.find("\n## ")
    return text[start:] if nxt < 0 else text[start : start + len(heading_prefix) + nxt]


def test_compare_litellm_pins_1105_ga_agent_vs_multi_agent() -> None:
    """1.105.0 is GA; agent/Lens vs on-box multi_agent, no Lens parity (#1640)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.105")
    lower = section.lower()
    assert "1.105.0" in section
    assert "ga" in lower
    assert "prerelease" not in lower
    assert "do not treat" not in lower
    assert "-rc" not in lower
    assert "litellm.agent" in lower
    assert "lens" in lower
    assert "multi_agent" in section
    assert "ledger" in lower
    assert "does **not** ship" in lower or "does not ship" in lower
    assert "lens parity" not in lower
    assert "/v1/decisions" in section
    assert "/v1/systemone" in section
    assert "1.104" in text


def test_compare_litellm_pins_1106_decision_model_guardrail() -> None:
    """1.106.0 is GA; decision-model guardrail is still not shipped (#1758)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.106")
    lower = section.lower()
    assert "1.106.0" in section
    assert "ga" in lower
    assert "prerelease" not in lower
    assert "-rc" not in lower
    assert " rc" not in lower
    assert "decision" in lower
    assert "guardrail" in lower
    assert "does **not** ship" in lower or "does not ship" in lower
    assert "/v1/decisions" in section
    assert "1.104" in text


def test_compare_litellm_pins_1105_ga_decisions_parity() -> None:
    """1.105.0 GA Decisions routes vs on-box /v1/decisions + /v1/systemone (#1584, #1640)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.105")
    lower = section.lower()
    assert "1.105.0" in section
    assert "ga" in lower
    assert "prerelease" not in lower
    assert "decisions" in lower
    assert "/v1/decisions" in section
    assert "/v1/systemone" in section
    assert "already" in lower
    # 1.105 itself is GA. The prerelease watch moved to 1.107 (#1758).
    watch = _markdown_section(text, "## LiteLLM 1.107")
    watch_lower = watch.lower()
    assert "prerelease" in watch_lower or "rc" in watch_lower
    assert "1.106.0" in watch
    assert "ga" in watch_lower
