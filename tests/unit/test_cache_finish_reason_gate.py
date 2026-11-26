"""Truncated, paused, or refused turns never reach L0/L1 (#2330).

Only complete turns are written to the $0 cache tiers, so a cache hit is
always a whole answer and a replay's ``finish_reason='stop'`` is truthful.
"""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from daari.router.stream_terminal import is_cacheable_finish_reason
from tests.conftest import NoopEmbedder
from tests.unit.test_router_org_cache import FakeOrgCacheClient

INCOMPLETE = ["length", "max_tokens", "pause_turn", "refusal", "content_filter"]


@pytest.mark.parametrize("reason", INCOMPLETE + ["LENGTH", " refusal "])
def test_incomplete_finish_reasons_are_not_cacheable(reason: str) -> None:
    assert is_cacheable_finish_reason(reason) is False


@pytest.mark.parametrize("reason", ["stop", "end_turn", "stop_sequence", "tool_calls", None, ""])
def test_complete_finish_reasons_are_cacheable(reason: str | None) -> None:
    assert is_cacheable_finish_reason(reason) is True


class _SpySemantic(SemanticCache):
    def __init__(self, path: str) -> None:
        super().__init__(path, NoopEmbedder(), enabled=True)
        self.put_calls = 0
        self.agent_prefix_calls = 0

    async def put(self, request, response):  # type: ignore[override]
        self.put_calls += 1

    async def put_agent_prefix(self, request, response):  # type: ignore[override]
        self.agent_prefix_calls += 1


class _Executor(OllamaExecutor):
    def __init__(self, *, text: str = "the answer that got cut", done_reason: str = "stop") -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")
        self.text = text
        self.done_reason = done_reason
        self.execute_calls = 0
        self.stream_calls = 0

    async def execute(self, request: InternalRequest) -> InternalResponse:  # type: ignore[override]
        self.execute_calls += 1
        return InternalResponse(
            content=self.text,
            model="llama3.2:3b",
            finish_reason=self.done_reason,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.stream_calls += 1
        yield {"message": {"content": self.text}}
        yield {"message": {"content": ""}, "done": True, "done_reason": self.done_reason}


def _request(text: str = "explain exact caches", *, tools: list | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)], model="daari", tools=tools
    )


def _router(tmp_path, executor, **kwargs) -> tuple[Router, _SpySemantic, FakeOrgCacheClient]:
    semantic = _SpySemantic(str(tmp_path / "l1"))
    org = FakeOrgCacheClient()
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=semantic,
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        org_cache_client=org,
        **kwargs,
    )
    return router, semantic, org


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _openai_finish_reasons(body: str) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        for choice in json.loads(line[6:]).get("choices", []):
            if choice.get("finish_reason"):
                out.append(choice["finish_reason"])
    return out


def _anthropic_stop_reasons(body: str) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[6:])
        if event.get("type") == "message_delta":
            out.append(event["delta"]["stop_reason"])
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["length", "pause_turn", "refusal"])
async def test_nonstream_incomplete_turn_is_served_but_never_cached(tmp_path, reason):
    executor = _Executor(done_reason=reason)
    router, semantic, org = _router(tmp_path, executor)
    request = _request()

    first = await router.route(request)
    second = await router.route(request)

    assert first.finish_reason == reason
    assert first.content == executor.text
    assert executor.execute_calls == 2, "identical repeat must re-execute, not hit L0"
    assert second.daari_meta.cache_hit is False
    assert router.cache.get(request) is None
    assert org.l0_put_calls == 0
    assert org.l1_put_calls == 0
    assert semantic.put_calls == 0
    assert semantic.agent_prefix_calls == 0


@pytest.mark.asyncio
async def test_nonstream_incomplete_agent_turn_skips_agent_prefix(tmp_path):
    executor = _Executor(done_reason="length")
    router, semantic, org = _router(tmp_path, executor)
    tools = [{"type": "function", "function": {"name": "run", "parameters": {}}}]
    request = _request("use the run tool", tools=tools)

    await router.route(request)

    assert router.cache.get(request) is None
    assert org.l0_put_calls == 0
    assert semantic.agent_prefix_calls == 0


@pytest.mark.asyncio
async def test_nonstream_complete_turn_still_caches_and_replays(tmp_path):
    executor = _Executor(done_reason="stop")
    router, semantic, org = _router(tmp_path, executor)
    request = _request()

    first = await router.route(request)
    second = await router.route(request)

    assert first.finish_reason == "stop"
    assert executor.execute_calls == 1
    assert second.daari_meta.cache_hit is True
    assert second.daari_meta.tier == "L0"
    assert second.finish_reason == "stop"
    assert org.l0_put_calls == 1
    assert semantic.put_calls == 1


@pytest.mark.asyncio
async def test_chat_stream_length_truncation_is_honest_and_not_cached(tmp_path):
    executor = _Executor(done_reason="length")
    router, semantic, _org = _router(tmp_path, executor)
    request = _request("stream me a long one")

    first = await _collect(router.stream_openai_chunks(request))
    second = await _collect(router.stream_openai_chunks(request))

    assert _openai_finish_reasons(first)[-1] == "length"
    assert _openai_finish_reasons(second)[-1] == "length"
    assert executor.stream_calls == 2, "truncated stream must not be replayed from L0"
    assert router.cache.get(request) is None
    assert semantic.put_calls == 0
    assert router.metrics.snapshot().get("L0", {}).get("cache_hits", 0) == 0


@pytest.mark.asyncio
async def test_chat_stream_complete_turn_still_hits_l0(tmp_path):
    executor = _Executor(done_reason="stop")
    router, semantic, _org = _router(tmp_path, executor)
    request = _request("stream me a short one")

    await _collect(router.stream_openai_chunks(request))
    second = await _collect(router.stream_openai_chunks(request))

    assert executor.stream_calls == 1
    assert _openai_finish_reasons(second)[-1] == "stop"
    assert router.cache.get(request) is not None
    assert semantic.put_calls == 1


@pytest.mark.asyncio
async def test_messages_stream_max_tokens_is_honest_and_not_cached(tmp_path):
    executor = _Executor(done_reason="length")
    router, _semantic, _org = _router(tmp_path, executor)
    request = _request("anthropic stream, truncated")

    first = await _collect(router.stream_anthropic_events(request))
    second = await _collect(router.stream_anthropic_events(request))

    assert _anthropic_stop_reasons(first)[-1] == "max_tokens"
    assert _anthropic_stop_reasons(second)[-1] == "max_tokens"
    assert executor.stream_calls == 2
    assert router.cache.get(request) is None


@pytest.mark.asyncio
async def test_messages_stream_complete_turn_still_hits_l0(tmp_path):
    executor = _Executor(done_reason="stop")
    router, _semantic, _org = _router(tmp_path, executor)
    request = _request("anthropic stream, complete")

    await _collect(router.stream_anthropic_events(request))
    second = await _collect(router.stream_anthropic_events(request))

    assert executor.stream_calls == 1
    assert _anthropic_stop_reasons(second)[-1] == "end_turn"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("done_reason", "expected"),
    [("length", "length"), ("stop", "stop"), (None, "stop"), ("pause_turn", "pause_turn")],
)
async def test_ollama_nonstream_done_reason_maps_to_finish_reason(
    monkeypatch, done_reason, expected
):
    """Non-stream Ollama truncation must be honest so the put gate can see it."""

    def handler(_request: httpx.Request) -> httpx.Response:
        body = {"message": {"role": "assistant", "content": "cut"}, "done": True}
        if done_reason is not None:
            body["done_reason"] = done_reason
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched_client)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    request = InternalRequest(model="llama3.2:3b", messages=[Message(role="user", content="hi")])

    response = await executor.execute(request)
    assert response.finish_reason == expected
