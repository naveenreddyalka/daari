"""Session affinity: pin a model across tool-turn continuations (#356)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from daari.router.session_affinity import SessionPinStore, conversation_prefix_hash, is_continuation
from tests.conftest import NoopEmbedder

LONG_PROMPT = "please explain this " + "word " * 300


def _pin_store(ttl: float = 30.0, now: list[float] | None = None) -> SessionPinStore:
    clock = (lambda: now[0]) if now is not None else None
    return SessionPinStore(ttl_seconds=ttl, clock=clock)


def _request(text: str, *, user: str | None = "agent-1", extra: list[Message] | None = None) -> InternalRequest:
    messages = [Message(role="user", content=text), *(extra or [])]
    request = InternalRequest(messages=messages, model="daari")
    request.meta.user = user
    request.meta.no_cache = True
    return request


def _continuation(text: str, *, user: str | None = "agent-1") -> InternalRequest:
    return _request(
        text,
        user=user,
        extra=[
            Message(
                role="assistant",
                content="",
                tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "read_file"}}],
            ),
            Message(role="tool", content="file contents", tool_call_id="call_1"),
        ],
    )


def _router(tmp_path, *, affinity: bool = True, ttl: float = 1800.0, calls: list[str] | None = None) -> Router:
    calls = calls if calls is not None else []

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            calls.append(_tier)
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1),
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
        session_affinity=affinity,
        session_affinity_ttl_seconds=ttl,
    )
    return router


def test_tool_continuation_and_unchanged_prefix():
    user = [Message(role="user", content="plan the change")]
    pin_prefix = conversation_prefix_hash(user)
    store = _pin_store()
    store.put("user:agent-1", tier="L4", model="model-l4", prefix_hash=pin_prefix)
    pin = store.get("user:agent-1")
    assert is_continuation(
        [
            *user,
            Message(role="assistant", tool_calls=[{"id": "c"}]),
            Message(role="tool", content="ok", tool_call_id="c"),
        ],
        pin,
    )
    assert is_continuation(user, pin)
    assert not is_continuation(
        [Message(role="user", content="a brand new question")],
        pin,
    )


def test_pin_expires(tmp_path):
    now = [10.0]
    store = _pin_store(ttl=5.0, now=now)
    store.put("user:agent-1", tier="L4", model="model-l4", prefix_hash="abc")
    assert store.get("user:agent-1") is not None
    now[0] = 16.0
    assert store.get("user:agent-1") is None


@pytest.mark.asyncio
async def test_continuation_replays_pin_and_new_user_turn_reroutes(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )

    calls: list[str] = []
    router = _router(tmp_path, calls=calls)
    first = await router.route(_request(LONG_PROMPT))
    assert first.daari_meta.tier == "L4"
    assert calls == ["L4"]

    second = await router.route(_continuation(LONG_PROMPT))
    assert second.daari_meta.tier == "L4"
    assert second.model == "model-l4"
    assert calls == ["L4", "L4"]
    assert any(event == "session_pin" for event, _ in events)

    third = await router.route(_request("short ask"))
    assert third.daari_meta.tier == "L3"
    assert calls[-1] == "L3"


@pytest.mark.asyncio
async def test_affinity_off_does_not_pin(tmp_path):
    calls: list[str] = []
    router = _router(tmp_path, affinity=False, calls=calls)
    await router.route(_request(LONG_PROMPT))
    follow = await router.route(_continuation("short ask"))
    # Continuation of a short user prefix would be L3 if heuristics rerun.
    # The long prompt pinned nothing, so the short continuation is classified
    # from its own user text (≤12 words → L3).
    assert follow.daari_meta.tier == "L3"
    assert calls == ["L4", "L3"]


@pytest.mark.asyncio
async def test_tier_cap_overrides_pin(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", lambda event, payload: events.append((event, payload)))
    calls: list[str] = []
    router = _router(tmp_path, calls=calls)
    await router.route(_request(LONG_PROMPT))
    capped = _continuation(LONG_PROMPT)
    capped.meta.tier_cap = "L3"
    response = await router.route(capped)
    assert response.daari_meta.tier == "L3"
    assert any(
        event == "session_pin_override" and payload.get("reason") == "tier_cap"
        for event, payload in events
    )


@pytest.mark.asyncio
async def test_expired_pin_reroutes(tmp_path):
    now = [100.0]
    calls: list[str] = []
    router = _router(tmp_path, ttl=5.0, calls=calls)
    router.session_pins = SessionPinStore(ttl_seconds=5.0, clock=lambda: now[0])
    await router.route(_request(LONG_PROMPT))
    now[0] = 200.0
    follow = await router.route(_continuation("short ask"))
    assert follow.daari_meta.tier == "L3"


HUGE_TOOL = "x" * 9000  # ~2250 tokens → would flip complexity to complex alone


@pytest.mark.asyncio
async def test_classify_user_turn_reuses_profile_on_tool_continuation(tmp_path, monkeypatch):
    from daari.observability.trace import TraceStore
    from daari.router.profile import build_prompt_profile

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path, affinity=False)
    router.classify_user_turn = True
    router.trace_store = TraceStore(tmp_path / "traces.sqlite3")

    first = await router.route(_request("write a small helper", user="u1"))
    first_profile = build_prompt_profile(
        InternalRequest(messages=[Message(role="user", content="write a small helper")], model="daari")
    )
    assert first.daari_meta.task_type == first_profile.category
    assert first.daari_meta.complexity == first_profile.complexity

    follow = _continuation("write a small helper", user="u1")
    # Inflate the tool payload so a fresh profile would become complex.
    follow.messages[-1] = Message(
        role="tool", content=HUGE_TOOL, tool_call_id="call_1"
    )
    fresh = build_prompt_profile(follow)
    assert fresh.complexity == "complex"

    second = await router.route(follow)
    assert second.daari_meta.task_type == first_profile.category
    assert second.daari_meta.complexity == first_profile.complexity
    assert any(
        event == "classify_user_turn" and payload.get("reused") is True
        for event, payload in events
    )
    stored = router.trace_store.get(second.daari_meta.trace_id)
    steps = [s["step"] for s in stored["steps"]]
    assert "classify_user_turn" in steps


@pytest.mark.asyncio
async def test_classify_user_turn_new_user_message_reprofiles(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path, affinity=False)
    router.classify_user_turn = True
    await router.route(_request("write a small helper", user="u1"))
    events.clear()
    third = await router.route(_request("please explain this " + "word " * 300, user="u1"))
    assert third.daari_meta.complexity == "complex"
    assert not any(event == "classify_user_turn" for event, _ in events)


@pytest.mark.asyncio
async def test_classify_user_turn_phase_routing_still_sees_tools(tmp_path, monkeypatch):
    """Phase routing must still inspect tool history when classify_user_turn is on."""
    from daari.router.phase import default_phase_map

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path, affinity=False)
    router.classify_user_turn = True
    router.phase_routing = True
    router.phase_map = default_phase_map()
    await router.route(_request(LONG_PROMPT, user="u1"))  # L4 from length
    # Explore-phase tool names should step L4 → L3.
    follow = _request(
        LONG_PROMPT,
        user="u1",
        extra=[
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            ),
            Message(role="tool", content="ok", tool_call_id="c1"),
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "grep", "arguments": "{}"},
                    }
                ],
            ),
            Message(role="tool", content="hit", tool_call_id="c2"),
        ],
    )
    response = await router.route(follow)
    assert response.daari_meta.tier == "L3"
    assert any(event == "phase_route" for event, _ in events)
    assert any(event == "classify_user_turn" and payload.get("reused") for event, payload in events)
