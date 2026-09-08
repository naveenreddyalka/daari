"""Stall detector: identical tool calls and error streaks (#357)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import Message
from daari.router.stall import bump_tier, detect_stall


def _call(name: str, arguments: str, *, call_id: str = "c") -> Message:
    return Message(
        role="assistant",
        content="",
        tool_calls=[
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    )


def _tool(content: str, call_id: str = "c") -> Message:
    return Message(role="tool", content=content, tool_call_id=call_id)


def test_identical_calls_within_window_trigger():
    messages = [Message(role="user", content="fix it")]
    for index in range(3):
        messages.append(_call("read_file", '{"path": "a.py"}', call_id=f"c{index}"))
        messages.append(_tool("print('hello')", f"c{index}"))
    match = detect_stall(messages, repeats=3, window=6)
    assert match is not None
    assert match.pattern == "repeat"
    assert match.count == 3


def test_argument_whitespace_does_not_hide_a_repeat():
    messages = [
        _call("read_file", '{"path":"a.py"}'),
        _call("read_file", '{ "path" : "a.py" }'),
        _call("read_file", '{"path": "a.py"}'),
    ]
    match = detect_stall(messages, repeats=3, window=6)
    assert match is not None
    assert match.pattern == "repeat"


def test_different_arguments_are_not_a_repeat():
    messages = [
        _call("read_file", '{"path": "a.py"}'),
        _call("read_file", '{"path": "b.py"}'),
        _call("read_file", '{"path": "c.py"}'),
    ]
    assert detect_stall(messages, repeats=3, window=6) is None


def test_repeats_outside_the_window_do_not_trigger():
    messages = []
    for index in range(3):
        messages.append(_call("read_file", '{"path": "a.py"}', call_id=f"old{index}"))
    for index in range(6):
        messages.append(_call("list_dir", f'{{"path": "{index}"}}', call_id=f"new{index}"))
    assert detect_stall(messages, repeats=3, window=6) is None


def test_consecutive_error_results_trigger():
    messages = [Message(role="user", content="retry")]
    for index, body in enumerate(
        ["Error: file missing", "Error: file missing", "Error: still missing"]
    ):
        messages.append(_call("read_file", f'{{"path": "{index}"}}', call_id=f"e{index}"))
        messages.append(_tool(body, f"e{index}"))
    match = detect_stall(messages, repeats=3, window=6)
    assert match is not None
    assert match.pattern == "error_streak"
    assert match.count == 3


def test_error_streak_breaks_on_a_successful_result():
    messages = [
        _tool("Error: no"),
        _tool("print('ok')"),
        _tool("Error: again"),
        _tool("Error: again"),
    ]
    assert detect_stall(messages, repeats=3, window=6) is None


def test_mention_of_error_inside_a_successful_payload_is_not_an_error():
    messages = [
        _tool("def handle_error():\n    return 1"),
        _tool("def handle_error():\n    return 1"),
        _tool("def handle_error():\n    return 1"),
    ]
    assert detect_stall(messages, repeats=3, window=6) is None


def test_bump_stops_at_cap_and_without_frontier():
    assert bump_tier("L3", frontier=False) == "L4"
    assert bump_tier("L4", frontier=False) == "L5"
    assert bump_tier("L5", frontier=False) is None
    assert bump_tier("L5", frontier=True) == "L6"


def _stalled_history(text: str = "hi") -> list[Message]:
    messages = [Message(role="user", content=text)]
    for index in range(3):
        messages.append(_call("read_file", '{"path": "a.py"}', call_id=f"c{index}"))
        messages.append(_tool("print('hello')", f"c{index}"))
    return messages


@pytest.mark.asyncio
async def test_router_stall_bumps_one_tier_and_respects_cap(tmp_path, monkeypatch):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    calls: list[str] = []

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            calls.append(_tier)
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", provider_id="ollama"),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        stall_escalation=True,
    )
    request = InternalRequest(messages=_stalled_history("hi"), model="daari")
    request.meta.no_cache = True
    response = await router.route(request)
    assert response.daari_meta.tier == "L4"
    assert calls == ["L4"]
    assert any(event == "stall_escalation" and payload.get("count") == 3 for event, payload in events)

    capped = InternalRequest(messages=_stalled_history("hi"), model="daari")
    capped.meta.no_cache = True
    capped.meta.tier_cap = "L3"
    held = await router.route(capped)
    assert held.daari_meta.tier == "L3"
