"""Phase routing: classify agent turns from tool history (#374)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import Message
from daari.router.phase import adjust_tier, classify_phase


def _call(name: str, arguments: str = "{}", *, call_id: str = "c") -> Message:
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


def _tool(content: str = "ok", call_id: str = "c") -> Message:
    return Message(role="tool", content=content, tool_call_id=call_id)


def _history(*names: str) -> list[Message]:
    messages = [Message(role="user", content="work")]
    for index, name in enumerate(names):
        messages.append(_call(name, call_id=f"c{index}"))
        messages.append(_tool("ok", f"c{index}"))
    return messages


def test_read_search_list_fetch_classify_explore():
    for name in ("read_file", "search_code", "list_dir", "fetch_url", "grep_files"):
        match = classify_phase(_history(name), window=6)
        assert match is not None
        assert match.phase == "explore"
        assert any(name.lower() == s.lower() for s in match.signals)


def test_edit_write_apply_classify_implement():
    for name in ("edit_file", "write_file", "apply_patch"):
        match = classify_phase(_history(name), window=6)
        assert match is not None
        assert match.phase == "implement"


def test_test_run_build_lint_classify_verify():
    for name in ("run_tests", "pytest", "build_project", "lint_files"):
        match = classify_phase(_history(name), window=6)
        assert match is not None
        assert match.phase == "verify"


def test_empty_or_unknown_history_returns_none():
    assert classify_phase([], window=6) is None
    assert classify_phase([Message(role="user", content="hi")], window=6) is None
    assert classify_phase(_history("unknown_tool", "mystery"), window=6) is None


def test_majority_in_window_wins():
    # Five explore + one implement in window → explore
    names = ["read_file", "read_file", "list_dir", "search_code", "fetch_docs", "write_file"]
    match = classify_phase(_history(*names), window=6)
    assert match is not None
    assert match.phase == "explore"


def test_window_limits_lookback():
    # Older writes outside window; recent reads dominate
    names = ["write_file", "write_file", "write_file", "read_file", "list_dir", "search_code"]
    match = classify_phase(_history(*names), window=3)
    assert match is not None
    assert match.phase == "explore"


def test_adjust_relative_delta_floors_at_l3():
    assert adjust_tier("L4", "explore", {"explore": -1, "implement": 0, "verify": 0}) == "L3"
    assert adjust_tier("L3", "explore", {"explore": -1, "implement": 0, "verify": 0}) == "L3"
    assert adjust_tier("L5", "explore", {"explore": -1, "implement": 0, "verify": 0}) == "L4"
    assert adjust_tier("L4", "implement", {"explore": -1, "implement": 0, "verify": 0}) == "L4"


def test_adjust_absolute_override():
    assert adjust_tier("L5", "explore", {"explore": "L3", "implement": 0, "verify": 0}) == "L3"
    assert adjust_tier("L3", "verify", {"explore": -1, "implement": 0, "verify": "L5"}) == "L5"


def test_adjust_unknown_tier_unchanged():
    assert adjust_tier("L6", "explore", {"explore": -1}) == "L6"
    assert adjust_tier("L0", "explore", {"explore": -1}) == "L0"


@pytest.mark.asyncio
async def test_router_explore_downgrades_one_tier(tmp_path, monkeypatch):
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
    long = "please explain this " + "word " * 300

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
        phase_routing=True,
    )
    messages = _history("read_file", "list_dir", "search_code")
    messages[0] = Message(role="user", content=long)
    request = InternalRequest(
        messages=messages,
        model="daari",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )
    request.meta.no_cache = True
    response = await router.route(request)
    assert response.daari_meta.tier == "L3"
    assert calls == ["L3"]
    assert any(
        event == "phase_route" and payload.get("phase") == "explore" for event, payload in events
    )


@pytest.mark.asyncio
async def test_router_stall_beats_phase_downgrade(tmp_path, monkeypatch):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

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
        phase_routing=True,
        stall_escalation=True,
    )
    # Short prompt → L3 heuristic; explore would stay L3; three identical reads stall → L4
    messages = [Message(role="user", content="hi")]
    for index in range(3):
        messages.append(_call("read_file", '{"path": "a.py"}', call_id=f"c{index}"))
        messages.append(_tool("print('hello')", f"c{index}"))
    request = InternalRequest(
        messages=messages,
        model="daari",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )
    request.meta.no_cache = True
    response = await router.route(request)
    assert response.daari_meta.tier == "L4"
    assert calls == ["L4"]


@pytest.mark.asyncio
async def test_router_phase_off_and_non_agent_unaffected(tmp_path, monkeypatch):
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
    long = "please explain this " + "word " * 300

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
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
        phase_routing=False,
    )
    messages = _history("read_file", "list_dir")
    messages[0] = Message(role="user", content=long)
    request = InternalRequest(
        messages=messages,
        model="daari",
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )
    request.meta.no_cache = True
    response = await router.route(request)
    assert response.daari_meta.tier == "L4"
    assert not any(event == "phase_route" for event, _ in events)

    plain = InternalRequest(messages=[Message(role="user", content=long)], model="daari")
    plain.meta.no_cache = True
    router_on = Router(
        cache=ExactCache(str(tmp_path / "l0b"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1b"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        phase_routing=True,
    )
    events.clear()
    plain_resp = await router_on.route(plain)
    assert plain_resp.daari_meta.tier == "L4"
    assert not any(event == "phase_route" for event, _ in events)
