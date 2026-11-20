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
    """1.106.x GA history; 1.106.7 final patch; decision-model still not shipped (#1758, #1929, #2019, #2122)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.106")
    lower = section.lower()
    assert "1.106.0" in section
    assert "1.106.6" in section
    assert "1.106.7" in section
    assert "ga" in lower
    assert "decision" in lower
    assert "guardrail" in lower
    assert "does **not** ship" in lower or "does not ship" in lower
    assert "/v1/decisions" in section
    assert "1.104" in text
    assert "releases/tag/v1.106.6" in text
    assert "releases/tag/v1.106.7" in text
    assert "e82a3c6" in section
    assert "cosign" in lower
    assert "emudhra" in lower or "emsign" in lower
    assert "distrust_emudhra_ca" in section
    assert "brotli" in lower or "image" in lower
    assert "1.109.1" in section


def test_compare_litellm_pins_1108_ga_lts_floor() -> None:
    """1.108 LTS history retained; live LTS patch is 1.108.7; floor moved to 1.109.1 (#2258)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.108")
    lower = section.lower()
    assert "1.108.2" in section
    assert "releases/tag/v1.108.2" in text
    assert "2026-11-06" in section
    assert "1.108.0" in section
    assert "releases/tag/v1.108.0" in text
    assert "2026-11-04" in section
    assert "1.108.7" in section
    assert "releases/tag/v1.108.7" in text
    assert "1.108.6" in section
    assert "releases/tag/v1.108.6" in text
    assert "1.108.5" in section
    assert "releases/tag/v1.108.5" in text
    assert "ga" in lower
    assert "lts" in lower
    assert "live" in lower and ("lts patch" in lower or "lts" in lower)
    assert "rc-only" not in lower
    assert "pending" not in lower or "not pending" in lower
    # Prior RC called out as superseded parity, not the floor.
    assert "1.108.0-rc.1" in section
    assert "parity" in lower
    assert "1.106.7" in section
    # Responses bridge honesty called out on the LTS line (#2258).
    assert "max_tool_calls" in section
    assert "failed" in lower and ("turn" in lower or "previous_response" in lower)
    # Stable floor is now 1.109.1 — 1.108 section must not claim current floor.
    assert "1.109.1" in section
    floor = _markdown_section(text, "## LiteLLM 1.109")
    assert "1.109.1" in floor
    assert "stable comparison floor" in floor.lower() or "comparison floor" in floor.lower()


def test_compare_litellm_pins_1108_lts_pilot_and_tuesday_cadence() -> None:
    """1.108 LTS pilot + Tuesday cadence are live; floor is 1.109.1 (#2258)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.108")
    lower = section.lower()
    assert "1.108.2" in section
    assert "1.108.7" in section
    assert "1.108.6" in section
    assert "1.108.0" in section
    assert "lts" in lower
    assert "tuesday" in lower
    assert "live" in lower
    assert "one month" in lower or "one-month" in lower
    assert (
        "no litellm runtime" in lower
        or "does **not** depend" in lower
        or "does not depend" in lower
        or "not a daari upgrade" in lower
        or "competitor ops" in lower
        or "local-first" in lower
    )
    compromise = _markdown_section(text, "## LiteLLM 1.107")
    assert "compromis" in compromise.lower()
    assert "1.109.1" in compromise


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
    assert "1.109.1" in section
    assert "does not depend" in lower or "does **not** depend" in lower
    assert "agent_access_default_deny" not in lower
    assert "prerelease rc watchables" not in lower
    assert "not a feature comparison bar" in lower or "do-not-install" in lower


def test_compare_litellm_pins_1109_ga_floor() -> None:
    """1.109.1 is GA stable comparison floor; 1.108.7 live LTS; hygiene + upgrade costs (#2258)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.109")
    lower = section.lower()
    assert "1.109.1" in section
    assert "releases/tag/v1.109.1" in section
    assert "2026-11-12" in section
    assert "1.109.0" in section
    assert "releases/tag/v1.109.0" in section
    assert "ga" in lower
    assert "stable comparison floor" in lower or "comparison floor" in lower
    assert "prerelease" not in lower or "superseded" in lower
    assert "do not promote" not in lower and "do **not** promote" not in lower
    assert "1.108.7" in section
    assert "releases/tag/v1.108.7" in text
    assert "51254" in section
    assert "credential" in lower or "hygiene" in lower
    assert "allowlist" in lower or "openai_payload" in section
    # Feature parity notes retained from the RC watch era.
    assert "mid-stream" in lower or "midstream" in lower
    assert "stream_fallback_continue" in section or "stream fallback" in lower
    assert "rpd" in lower or "requests-per-day" in lower or "request/token" in lower
    assert "tpd" in lower or "tokens-per-day" in lower or "token-per-day" in lower
    assert "x-litellm-priority" in lower
    assert "drop_params" in lower or "speed" in lower
    assert "agent_access_default_deny" in section
    assert "pricing_provider" in section
    # Five action-required migration items as upgrade-cost evidence.
    assert "fallback" in lower and "list" in lower
    assert "disk" in lower and ("cache" in lower or "diskcache" in lower)
    assert "48114" in section
    assert "rpm" in lower or "rate_limit" in lower or "enforce_model_rate_limits" in lower
    assert "gemini" in lower
    assert "drop_params" in lower
    assert "lens" in lower and "helm" in lower
    # Disk-cache removal vs daari L1 positioning (factual).
    assert "diskcache" in lower or "disk cache" in lower
    assert "l1" in lower or "l0" in lower or "semantic" in lower
    assert "lens parity" not in lower
    lts = _markdown_section(text, "## LiteLLM 1.108")
    assert "1.108.7" in lts
    assert "1.108.6" in lts
    assert "1.108.5" in lts
    assert "1.108.2" in lts
    assert "1.108.0" in lts
    assert "ga" in lts.lower()
    assert "lts" in lts.lower()


def test_compare_litellm_pins_1110_dev_watch_keep_ga_floor() -> None:
    """1.110.0-dev.1 is prerelease watch only; GA floor is 1.109.1 (#2252)."""
    text = DOC.read_text(encoding="utf-8")
    section = _markdown_section(text, "## LiteLLM 1.110")
    lower = section.lower()
    assert "1.110.0-dev.1" in section or "v1.110.0-dev.1" in section
    assert "releases/tag/v1.110.0-dev.1" in section
    assert "prerelease" in lower
    assert "watch" in lower
    assert "do not promote" in lower or "do **not** promote" in lower
    assert "1.110" in section
    assert "1.109.1" in section
    # Do not promote 1.110 to the floor.
    floor = _markdown_section(text, "## LiteLLM 1.109")
    assert "1.109.1" in floor
    assert "1.110" not in floor
