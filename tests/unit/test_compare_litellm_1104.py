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
    """1.106.x is GA; floor 1.106.3; decision-model guardrail still not shipped (#1758, #1910)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.106")
    lower = section.lower()
    assert "1.106.0" in section
    assert "1.106.3" in section
    assert "ga" in lower
    assert "prerelease" not in lower
    assert "-rc" not in lower
    assert " rc" not in lower
    assert "decision" in lower
    assert "guardrail" in lower
    assert "does **not** ship" in lower or "does not ship" in lower
    assert "/v1/decisions" in section
    assert "1.104" in text
    assert "releases/tag/v1.106.3" in text
    assert "e82a3c6" in section
    assert "cosign" in lower
    assert "emudhra" in lower
    assert "distrust_emudhra_ca" in section


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


def test_compare_litellm_pins_1107_compromise_advisory() -> None:
    """1.107.0 is a supply-chain compromise advisory, not an RC feature watch (#1848)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.107")
    lower = section.lower()
    assert "compromise" in lower or "compromised" in lower
    assert "do not" in lower or "do-not-install" in lower
    assert "litellm==1.107.0" in text
    assert "litellm/litellm:1.107.0" in text
    assert "aikido.dev" in lower
    assert "1.106.3" in section
    assert "does not depend" in lower or "does **not** depend" in lower
    assert "agent_access_default_deny" not in lower
    assert "prerelease rc watchables" not in lower
    assert "not a feature comparison bar" in lower or "do-not-install" in lower
