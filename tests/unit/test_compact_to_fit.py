"""Opt-in compact-to-fit before L6 (issue #1340, #1351)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.compact_to_fit import compact_messages, estimate_tokens
from daari.router.router import AppContext
from daari.server.app import create_app

ROOT = Path(__file__).resolve().parents[2]
ROUTING_TIERS = ROOT / "docs/developer/concepts/routing-tiers.md"


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


def test_disabled_router_path_omits_meta_and_counter(settings) -> None:
    settings.routing.compact_to_fit.enabled = False
    ctx = AppContext.from_settings(settings)
    request = InternalRequest(messages=[_user(i) for i in range(20)], model="m")
    out = ctx.router._compact_to_fit_for_frontier(request)
    assert out.meta.compact_to_fit is None
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap.get("compact_to_fit_applied", 0) == 0
    assert snap.get("compact_to_fit_tokens_dropped", 0) == 0


def test_enabled_over_budget_l6_path_sets_meta_and_increments(settings) -> None:
    settings.routing.compact_to_fit.enabled = True
    settings.routing.compact_to_fit.max_messages = 3
    ctx = AppContext.from_settings(settings)
    request = InternalRequest(messages=[_user(i) for i in range(10)], model="m")
    expected_before = estimate_tokens(request.messages)
    out = ctx.router._compact_to_fit_for_frontier(request)
    compact = out.meta.compact_to_fit
    assert compact is not None
    assert compact["messages_before"] == 10
    assert compact["messages_after"] == 3
    assert compact["messages_after"] < compact["messages_before"]
    assert compact["tokens_before"] == expected_before
    assert compact["tokens_after"] == estimate_tokens(out.messages)
    assert compact["tokens_after"] < compact["tokens_before"]
    response = InternalResponse(
        content="ok",
        model="m",
        daari_meta=DaariMeta(tier="L6", executor="openai", latency_ms=1),
    )
    ctx.router._copy_compact_to_fit_meta(out, response)
    assert response.daari_meta.compact_to_fit == compact
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap["compact_to_fit_applied"] == 1
    dropped = compact["tokens_before"] - compact["tokens_after"]
    assert snap["compact_to_fit_tokens_dropped"] == dropped
    assert dropped > 0


def test_tool_protected_history_does_not_claim_successful_trim(settings) -> None:
    settings.routing.compact_to_fit.enabled = True
    settings.routing.compact_to_fit.max_messages = 2
    ctx = AppContext.from_settings(settings)
    messages = [
        Message(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "f"}}],
        ),
        Message(role="tool", content="result", tool_call_id="call_1"),
        Message(role="system", content="sys"),
    ]
    request = InternalRequest(messages=messages, model="m")
    out = ctx.router._compact_to_fit_for_frontier(request)
    assert len(out.messages) == 3
    assert out.meta.compact_to_fit is None
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap.get("compact_to_fit_applied", 0) == 0
    assert snap.get("compact_to_fit_tokens_dropped", 0) == 0


@pytest.mark.asyncio
async def test_stats_compact_counter_default_zero_and_after_trim(settings) -> None:
    settings.routing.compact_to_fit.enabled = True
    settings.routing.compact_to_fit.max_messages = 3
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json().get("compact_to_fit_applied", 0) == 0
        assert before.json().get("compact_to_fit_tokens_dropped", 0) == 0
        trimmed = app.state.ctx.router._compact_to_fit_for_frontier(
            InternalRequest(messages=[_user(i) for i in range(10)], model="m")
        )
        after = await client.get("/v1/daari/stats")
    assert after.status_code == 200
    assert after.json()["compact_to_fit_applied"] == 1
    compact = trimmed.meta.compact_to_fit
    assert compact is not None
    assert after.json()["compact_to_fit_tokens_dropped"] == (
        compact["tokens_before"] - compact["tokens_after"]
    )


def test_routing_tiers_docs_note_compact_meta() -> None:
    text = ROUTING_TIERS.read_text(encoding="utf-8")
    assert "compact_to_fit" in text
    assert "daari_meta.compact_to_fit" in text or "messages_before" in text
