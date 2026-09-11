"""classify_user_turn + agent User-Agent shortcut (#421)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.agent_ua import is_classify_user_turn_agent, sniff_agent_client_id
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.profile import build_prompt_profile
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

HUGE_TOOL = "x" * 9000  # ~2250 tokens → would flip complexity to complex alone


def _request(
    text: str,
    *,
    user: str | None = "u1",
    client_id: str | None = None,
    user_agent: str | None = None,
    extra: list[Message] | None = None,
) -> InternalRequest:
    messages = [Message(role="user", content=text), *(extra or [])]
    request = InternalRequest(messages=messages, model="daari")
    request.meta.user = user
    request.meta.client_id = client_id
    request.meta.user_agent = user_agent
    request.meta.no_cache = True
    return request


def _continuation(
    text: str,
    *,
    user: str | None = "u1",
    client_id: str | None = None,
    user_agent: str | None = None,
) -> InternalRequest:
    return _request(
        text,
        user=user,
        client_id=client_id,
        user_agent=user_agent,
        extra=[
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file"},
                    }
                ],
            ),
            Message(role="tool", content="file contents", tool_call_id="call_1"),
        ],
    )


def _router(
    tmp_path,
    *,
    classify_user_turn: bool = False,
    classify_user_turn_agents: bool = True,
) -> Router:
    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content="A confident answer with plenty of length to avoid escalation.",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(
                    tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        classify_user_turn=classify_user_turn,
        classify_user_turn_agents=classify_user_turn_agents,
    )


@pytest.mark.parametrize(
    "ua,expected",
    [
        ("Cursor/1.2", "cursor"),
        ("claude-code/2.0", "claude-code"),
        ("Claude Code CLI", "claude-code"),
        ("openai-codex/0.1", "codex"),
        ("python-httpx/0.28", None),
    ],
)
def test_sniff_agent_client_id(ua: str, expected: str | None):
    assert sniff_agent_client_id(ua) == expected


@pytest.mark.parametrize(
    "user_agent,client_id,expected",
    [
        ("Cursor/1.0", None, True),
        ("claude-code", None, True),
        ("Claude Code", None, True),
        ("codex-cli", None, True),
        (None, "cursor", True),
        (None, "claude-code", True),
        (None, "codex", True),
        ("python-httpx", None, False),
        (None, "sdk", False),
        (None, None, False),
    ],
)
def test_is_classify_user_turn_agent(
    user_agent: str | None, client_id: str | None, expected: bool
):
    assert is_classify_user_turn_agent(user_agent=user_agent, client_id=client_id) is expected


@pytest.mark.asyncio
async def test_agent_ua_reuses_when_classify_user_turn_default_off(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)  # defaults: classify off, agents on
    assert router.classify_user_turn is False
    assert router.classify_user_turn_agents is True

    first_profile = build_prompt_profile(
        InternalRequest(
            messages=[Message(role="user", content="write a small helper")], model="daari"
        )
    )
    await router.route(_request("write a small helper", user_agent="Cursor/1.0"))

    follow = _continuation("write a small helper", user_agent="Cursor/1.0")
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    assert build_prompt_profile(follow).complexity == "complex"

    second = await router.route(follow)
    assert second.daari_meta.task_type == first_profile.category
    assert second.daari_meta.complexity == first_profile.complexity
    assert any(
        event == "classify_user_turn"
        and payload.get("reused") is True
        and payload.get("source") == "ua"
        for event, payload in events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_agent",
    ["claude-code/2.0", "Claude Code/1.0", "openai-codex/0.1"],
)
async def test_other_agent_uas_reuse(tmp_path, monkeypatch, user_agent: str):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)
    await router.route(_request("write a small helper", user_agent=user_agent))
    follow = _continuation("write a small helper", user_agent=user_agent)
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    second = await router.route(follow)
    first_profile = build_prompt_profile(
        InternalRequest(
            messages=[Message(role="user", content="write a small helper")], model="daari"
        )
    )
    assert second.daari_meta.complexity == first_profile.complexity
    assert any(
        event == "classify_user_turn" and payload.get("source") == "ua"
        for event, payload in events
    )


@pytest.mark.asyncio
async def test_agents_flag_false_disables_ua_shortcut(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path, classify_user_turn=False, classify_user_turn_agents=False)
    await router.route(_request("write a small helper", user_agent="Cursor/1.0"))
    follow = _continuation("write a small helper", user_agent="Cursor/1.0")
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    second = await router.route(follow)
    assert second.daari_meta.complexity == "complex"
    assert not any(event == "classify_user_turn" for event, _ in events)


@pytest.mark.asyncio
async def test_anonymous_client_does_not_reuse_when_default_off(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)
    await router.route(_request("write a small helper", user_agent="python-httpx/0.28"))
    follow = _continuation("write a small helper", user_agent="python-httpx/0.28")
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    second = await router.route(follow)
    assert second.daari_meta.complexity == "complex"
    assert not any(event == "classify_user_turn" for event, _ in events)


@pytest.mark.asyncio
async def test_explicit_classify_user_turn_applies_to_every_client(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path, classify_user_turn=True, classify_user_turn_agents=False)
    first_profile = build_prompt_profile(
        InternalRequest(
            messages=[Message(role="user", content="write a small helper")], model="daari"
        )
    )
    await router.route(_request("write a small helper", user_agent="python-httpx/0.28"))
    follow = _continuation("write a small helper", user_agent="python-httpx/0.28")
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    second = await router.route(follow)
    assert second.daari_meta.complexity == first_profile.complexity
    assert any(
        event == "classify_user_turn"
        and payload.get("reused") is True
        and payload.get("source") == "config"
        for event, payload in events
    )


@pytest.mark.asyncio
async def test_client_id_cursor_triggers_ua_shortcut(tmp_path, monkeypatch):
    """Sniffed client_id alone (no raw UA on meta) still enables the shortcut."""
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)
    await router.route(_request("write a small helper", client_id="cursor"))
    follow = _continuation("write a small helper", client_id="cursor")
    follow.messages[-1] = Message(role="tool", content=HUGE_TOOL, tool_call_id="call_1")
    second = await router.route(follow)
    first_profile = build_prompt_profile(
        InternalRequest(
            messages=[Message(role="user", content="write a small helper")], model="daari"
        )
    )
    assert second.daari_meta.complexity == first_profile.complexity
    assert any(
        event == "classify_user_turn" and payload.get("source") == "ua"
        for event, payload in events
    )
