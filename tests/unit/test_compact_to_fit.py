"""Opt-in compact-to-fit before L6 (issue #1340)."""

from __future__ import annotations

from daari.config.settings import Settings
from daari.gateway.internal import Message
from daari.router.compact_to_fit import compact_messages


def _user(n: int, *, size: int = 8) -> Message:
    return Message(role="user", content=f"u{n}" + ("x" * size))


def test_disabled_leaves_history_unchanged() -> None:
    messages = [_user(i) for i in range(20)]
    out, before, after = compact_messages(
        messages, enabled=False, max_messages=4, max_tokens=1
    )
    assert out == messages
    assert before == after == 20


def test_empty_and_short_history_unchanged_when_enabled() -> None:
    empty, b0, a0 = compact_messages([], enabled=True, max_messages=8)
    assert empty == []
    assert b0 == a0 == 0

    short = [Message(role="system", content="sys"), _user(1)]
    out, before, after = compact_messages(short, enabled=True, max_messages=8)
    assert out == short
    assert before == after == 2


def test_enabled_over_budget_shrinks_oldest_droppable() -> None:
    messages = [_user(i) for i in range(10)]
    out, before, after = compact_messages(messages, enabled=True, max_messages=3)
    assert before == 10
    assert after == 3
    assert [m.content[:2] for m in out] == ["u7", "u8", "u9"]


def test_does_not_drop_tool_call_payloads() -> None:
    messages = [
        _user(0),
        Message(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "f"}}],
        ),
        Message(role="tool", content="result", tool_call_id="call_1"),
        _user(1),
        _user(2),
    ]
    out, _, after = compact_messages(messages, enabled=True, max_messages=3)
    assert after <= 4
    roles = [m.role for m in out]
    assert "tool" in roles
    assert any(m.tool_calls for m in out)


def test_enabled_token_budget_shrinks() -> None:
    messages = [_user(i, size=80) for i in range(8)]
    out, before, after = compact_messages(
        messages, enabled=True, max_messages=32, max_tokens=40
    )
    assert after < before
    assert len(out) < 8


def test_settings_default_off() -> None:
    settings = Settings()
    assert settings.routing.compact_to_fit.enabled is False
    assert settings.routing.compact_to_fit.max_messages == 32
    assert settings.routing.compact_to_fit.max_tokens == 0
