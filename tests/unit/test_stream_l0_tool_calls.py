"""Streamed L0 must not text-only-replay a tool-bearing cached response (#2234).

Choice: non-stream L0 put excludes responses with tool_calls (parity with the
stream put guards that already skip when tool_calls_sent / tool_use_sent).
"""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

TOOL_CALLS = [
    {
        "id": "c1",
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }
]


def _request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="look something up")],
        model="llama3.2:3b",
        tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
    )


def _tool_response() -> InternalResponse:
    return InternalResponse(
        content="calling tool",
        model="llama3.2:3b",
        tool_calls=TOOL_CALLS,
        finish_reason="tool_calls",
        daari_meta=DaariMeta(
            tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
        ),
    )


def _text_response() -> InternalResponse:
    return InternalResponse(
        content="plain cached answer about tools",
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
        ),
    )


def _router(tmp_path, *, execute_response: InternalResponse) -> tuple[Router, list[str]]:
    seen: list[str] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen.append("execute")
        return execute_response.model_copy(deep=True)

    async def fake_stream(request: InternalRequest):
        seen.append("stream")
        yield {"message": {"content": execute_response.content or ""}}
        if execute_response.tool_calls:
            yield {
                "message": {
                    "content": "",
                    "tool_calls": execute_response.tool_calls,
                }
            }
        yield {"done": True}

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    ollama.stream = fake_stream  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"), NoopEmbedder(), enabled=False
        ),
        ollama=ollama,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
    )
    return router, seen


def _stream_has_tool_calls(chunks: list[str]) -> bool:
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload = json.loads(line[len("data: ") :])
            for choice in payload.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("tool_calls"):
                    return True
                if choice.get("finish_reason") == "tool_calls":
                    return True
    return False


def _stream_is_text_only_stop(chunks: list[str]) -> bool:
    """True when the stream looks like the old buggy L0 replay (content + stop)."""
    saw_content = False
    saw_tool = False
    finish = None
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload = json.loads(line[len("data: ") :])
            for choice in payload.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    saw_content = True
                if delta.get("tool_calls"):
                    saw_tool = True
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
    return saw_content and not saw_tool and finish == "stop"


@pytest.mark.asyncio
async def test_nonstream_tool_calls_response_not_written_to_l0(tmp_path):
    router, seen = _router(tmp_path, execute_response=_tool_response())
    request = _request()
    result = await router.route(request)
    assert result.tool_calls
    assert seen == ["execute"]
    assert router.cache.get(request) is None


@pytest.mark.asyncio
async def test_stream_after_nonstream_tool_calls_never_text_only_replay(tmp_path):
    router, seen = _router(tmp_path, execute_response=_tool_response())
    request = _request()
    await router.route(request)
    chunks = [c async for c in router.stream_openai_chunks(request)]
    assert "stream" in seen, "must miss L0 and generate rather than text-only replay"
    assert not _stream_is_text_only_stop(chunks)


@pytest.mark.asyncio
async def test_stream_skips_legacy_l0_entry_with_tool_calls(tmp_path):
    """Defensive: a pre-fix entry with tool_calls must not text-only replay."""
    router, seen = _router(tmp_path, execute_response=_tool_response())
    request = _request()
    router.cache.put(request, _tool_response())
    chunks = [c async for c in router.stream_openai_chunks(request)]
    assert "stream" in seen
    assert not _stream_is_text_only_stop(chunks)
    assert _stream_has_tool_calls(chunks)


@pytest.mark.asyncio
async def test_stream_cache_hit_unchanged_for_pure_text(tmp_path):
    router, seen = _router(tmp_path, execute_response=_text_response())
    request = InternalRequest(
        messages=[Message(role="user", content="hello cache")],
        model="llama3.2:3b",
    )
    await router.route(request)
    assert router.cache.get(request) is not None
    chunks = [c async for c in router.stream_openai_chunks(request)]
    assert seen == ["execute"], "pure-text L0 stream hit must not re-execute"
    assert _stream_is_text_only_stop(chunks)
    snap = router.metrics.snapshot()
    assert snap["L0"]["cache_hits"] == 1
