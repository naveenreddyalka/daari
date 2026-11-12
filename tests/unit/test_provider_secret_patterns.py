"""Prebuilt OpenAI / Anthropic / Gemini credential patterns (#2186)."""

from __future__ import annotations

from pathlib import Path

from daari.gateway.guardrails import GuardrailEngine, GuardrailRule

OPENAI_KEY = "sk-" + ("a" * 48)
OPENAI_PROJ = "sk-proj-" + ("b" * 40)
ANTHROPIC_KEY = "sk-ant-" + ("c" * 40)
GEMINI_KEY = "AIza" + ("d" * 35)


def _secret_engine(*, action: str = "redact") -> GuardrailEngine:
    return GuardrailEngine(
        enabled=True,
        input_rules=[GuardrailRule(name="secrets", kind="secret", action=action)],
        output_rules=[GuardrailRule(name="secrets", kind="secret", action=action)],
    )


def test_output_redacts_openai_anthropic_gemini_keys():
    engine = _secret_engine()
    for key, kind in (
        (OPENAI_KEY, "openai_key"),
        (OPENAI_PROJ, "openai_key"),
        (ANTHROPIC_KEY, "anthropic_key"),
        (GEMINI_KEY, "gemini_key"),
    ):
        rewritten, result = engine.check_output_text(f"token {key} leaked")
        assert result.hits, key
        assert result.hits[0].rule == f"secret:{kind}"
        assert result.hits[0].kind == "secret"
        assert key not in rewritten
        assert f"<{kind}>" in rewritten


def test_input_redacts_provider_keys():
    engine = _secret_engine()
    for key, kind in (
        (OPENAI_KEY, "openai_key"),
        (ANTHROPIC_KEY, "anthropic_key"),
        (GEMINI_KEY, "gemini_key"),
    ):
        result = engine.check_input_text(f"please use {key}")
        assert result.hits, key
        assert result.hits[0].rule == f"secret:{kind}"
        assert result.rewritten is not None
        assert key not in result.rewritten
        assert f"<{kind}>" in result.rewritten


def test_input_block_uses_secret_kind_metadata():
    engine = _secret_engine(action="block")
    result = engine.check_input_text(f"exfil {OPENAI_KEY}")
    assert result.blocked
    assert result.hits[0].rule == "secret:openai_key"
    assert result.hits[0].kind == "secret"


def test_short_sk_fragment_does_not_trip():
    engine = _secret_engine()
    for fragment in ("sk-abc", "sk-short", "sk-proj-tiny", "AIzaShort", "ask-me-later"):
        result = engine.check_input_text(f"prose mentions {fragment} casually")
        assert not result.hits, fragment
        rewritten, out = engine.check_output_text(f"model said {fragment}")
        assert not out.hits, fragment
        assert fragment in rewritten


def test_guardrails_docs_name_provider_builtins():
    text = Path("docs/developer/guides/features/guardrails.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "openai" in lower
    assert "anthropic" in lower
    assert "gemini" in lower
