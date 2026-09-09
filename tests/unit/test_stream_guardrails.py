"""Incremental streaming output guardrail tests (#375)."""

from __future__ import annotations

from daari.gateway.guardrails import (
    GuardrailEngine,
    GuardrailRule,
    IncrementalOutputScanner,
)

AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


def _engine(*, action: str = "redact", deny: str | None = None) -> GuardrailEngine:
    rules = [GuardrailRule(name="secrets", kind="secret", action=action)]  # type: ignore[arg-type]
    if deny:
        rules.append(
            GuardrailRule(name="deny-word", kind="deny", pattern=deny, action="block")
        )
    return GuardrailEngine(enabled=True, output_rules=rules, block_message="BLOCKED")


def test_aws_key_split_across_deltas_is_redacted_before_emission():
    scanner = IncrementalOutputScanner(_engine(action="redact"), holdback=256)
    first = scanner.push("the key is AKIAIOSFODNN")
    assert AWS_KEY not in first.text
    assert "AKIA" not in first.text  # held entirely (under holdback)
    second = scanner.push("7EXAMPLE keep it")
    assert AWS_KEY not in second.text
    assert "AKIA" not in second.text
    final = scanner.flush()
    emitted = first.text + second.text + final.text
    assert AWS_KEY not in emitted
    assert "<aws_key>" in emitted
    assert scanner.scanned_text == emitted or "<aws_key>" in scanner.scanned_text
    assert AWS_KEY not in scanner.scanned_text


def test_block_rule_mid_stream_emits_block_message():
    scanner = IncrementalOutputScanner(
        _engine(action="redact", deny="forbidden"), holdback=8
    )
    # Build past holdback with safe text, then trip the deny rule.
    safe = scanner.push("hello world ")
    assert not safe.blocked
    hit = scanner.push("forbidden token")
    assert hit.blocked
    assert "BLOCKED" in hit.text or hit.text == ""
    # After block, further pushes stay blocked.
    again = scanner.push("more")
    assert again.blocked


def test_holdback_flushes_fully_at_stream_end():
    scanner = IncrementalOutputScanner(_engine(action="redact"), holdback=256)
    mid = scanner.push("short answer")
    assert mid.text == ""  # held under window
    end = scanner.flush()
    assert end.text == "short answer"
    assert scanner.scanned_text == "short answer"


def test_empty_chunks_and_flush():
    scanner = IncrementalOutputScanner(
        GuardrailEngine(
            enabled=True,
            output_rules=[GuardrailRule(name="secrets", kind="secret", action="redact")],
        ),
        holdback=16,
    )
    assert scanner.push("").text == ""
    scanner.push("hello world")
    assert scanner.flush().text == "hello world"
    assert scanner.scanned_text == "hello world"
