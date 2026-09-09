import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

USER_ASK = "write a unit test for the parser"


def _request(text: str, *, extra: list[Message] | None = None) -> InternalRequest:
    request = InternalRequest(
        messages=[Message(role="user", content=text), *(extra or [])],
        model="daari",
    )
    request.meta.user = "agent-1"
    request.meta.no_cache = True
    return request


def _continuation(text: str, *, tool_blob: str) -> InternalRequest:
    return _request(
        text,
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
            Message(role="tool", content=tool_blob, tool_call_id="call_1"),
        ],
    )


def _router(tmp_path, *, classify: bool = True) -> Router:
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A confident answer with plenty of length to avoid escalation.",
            model="model-l3",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    executor = OllamaExecutor(base_url="http://test", default_model="model-l3", tier="L3")
    executor.execute = fake_execute  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        classify_user_turn=classify,
    )


@pytest.mark.asyncio
async def test_continuation_reuses_category_and_complexity(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)
    first = await router.route(_request(USER_ASK))
    huge = "x" * 9000
    second = await router.route(_continuation(USER_ASK, tool_blob=huge))
    assert first.daari_meta.task_type == "test"
    assert second.daari_meta.task_type == "test"
    assert first.daari_meta.complexity == second.daari_meta.complexity
    reused = [
        payload
        for event, payload in events
        if event == "classify_user_turn" and payload.get("reused")
    ]
    assert reused


@pytest.mark.asyncio
async def test_off_reprofiles_when_tool_blob_grows(tmp_path):
    router = _router(tmp_path, classify=False)
    first = await router.route(_request(USER_ASK))
    huge = "x" * 9000
    second = await router.route(_continuation(USER_ASK, tool_blob=huge))
    assert first.daari_meta.complexity != "complex"
    assert second.daari_meta.complexity == "complex"


@pytest.mark.asyncio
async def test_new_user_message_reprofiles(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    router = _router(tmp_path)
    await router.route(_request(USER_ASK))
    follow = await router.route(_request("please explain this " + "word " * 300))
    assert follow.daari_meta.task_type != "test"
    reused = [
        payload
        for event, payload in events
        if event == "classify_user_turn" and payload.get("reused")
    ]
    assert not reused


def test_setting_defaults_off():
    assert Settings().routing.classify_user_turn is False
