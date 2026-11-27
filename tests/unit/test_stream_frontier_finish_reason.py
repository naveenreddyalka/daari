"""Frontier streamed legs surface the upstream terminal finish_reason (#2331)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.observability.metrics import Metrics
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router
from daari.router.stream_terminal import resolve_stream_finish_reason
from tests.conftest import NoopEmbedder


def _request(text: str = "explain quantum decoherence", **meta) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(**meta),
    )


def _finish_reasons(body: str) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        for choice in payload.get("choices", []):
            if choice.get("finish_reason"):
                out.append(choice["finish_reason"])
    return out


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


@pytest.mark.parametrize(
    ("upstream", "tool_calls_sent", "expected"),
    [
        (None, False, "stop"),
        (None, True, "tool_calls"),
        ("stop", False, "stop"),
        ("stop", True, "tool_calls"),
        ("end_turn", True, "tool_calls"),
        ("length", False, "length"),
        ("max_tokens", False, "length"),
        ("max_tokens", True, "length"),
        ("tool_use", True, "tool_calls"),
        ("tool_calls", False, "tool_calls"),
        ("pause_turn", False, "pause_turn"),
        ("refusal", False, "refusal"),
        ("content_filter", False, "content_filter"),
        ("  Content_Filter ", False, "content_filter"),
    ],
)
def test_resolve_stream_finish_reason(upstream, tool_calls_sent, expected):
    assert resolve_stream_finish_reason(upstream, tool_calls_sent=tool_calls_sent) == expected


def _sse_response(body: str | bytes) -> httpx.Response:
    raw = body.encode() if isinstance(body, str) else body
    return httpx.Response(200, content=raw, headers={"content-type": "text/event-stream"})


@pytest.mark.asyncio
async def test_frontier_stream_emits_openai_finish_reason_event():
    body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"cut"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
        "data: [DONE]\n\n"
    )
    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(lambda _r: _sse_response(body)),
    )
    events = [e async for e in executor.stream(_request(), escalated_from="L3", local_confidence=0.1)]
    assert "cut" in events
    assert {"finish_reason": "length"} in events


@pytest.mark.asyncio
async def test_frontier_stream_emits_anthropic_stop_reason_event():
    body = (
        'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":"cut"}}\n\n'
        'event: message_delta\ndata: {"type":"message_delta",'
        '"delta":{"stop_reason":"max_tokens","stop_sequence":null},"usage":{"output_tokens":9}}\n\n'
        'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    )
    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(lambda _r: _sse_response(body)),
    )
    events = [e async for e in executor.stream(_request(), escalated_from="L3", local_confidence=0.1)]
    assert "cut" in events
    assert {"finish_reason": "max_tokens"} in events


class _LocalIdk(OllamaExecutor):
    def __init__(self) -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"role": "assistant", "content": "idk"}}
        yield {"done": True, "done_reason": "stop"}

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="idk",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )


class _ScriptedFrontier:
    api_key = "sk-test"

    def __init__(self, events: list) -> None:
        self.events = events
        self.stream_calls = 0
        self.breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)

    async def execute(self, request, escalated_from=None, local_confidence=None):
        raise AssertionError("relay must use stream, not execute")

    async def stream(self, request, escalated_from=None, local_confidence=None):
        self.stream_calls += 1
        for event in self.events:
            yield event


def _relay_router(tmp_path, frontier, **kwargs) -> Router:
    local = _LocalIdk()
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        frontier=frontier,
        metrics=Metrics(),
        frontier_enabled=True,
        confidence_threshold=0.99,
        **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream", "expected"),
    [("length", "length"), ("max_tokens", "length"), ("pause_turn", "pause_turn"), ("refusal", "refusal")],
)
async def test_relay_terminal_chunk_mirrors_upstream_finish_reason(tmp_path, upstream, expected):
    frontier = _ScriptedFrontier(["FRONTIER ", "TEXT", {"finish_reason": upstream}])
    router = _relay_router(tmp_path, frontier)
    body = await _collect(router.stream_openai_chunks(_request()))
    assert frontier.stream_calls == 1
    assert "FRONTIER " in body
    assert _finish_reasons(body) == [expected]


@pytest.mark.asyncio
async def test_relay_terminal_chunk_defaults_to_stop_without_event(tmp_path):
    frontier = _ScriptedFrontier(["plain ", "text"])
    router = _relay_router(tmp_path, frontier)
    body = await _collect(router.stream_openai_chunks(_request()))
    assert _finish_reasons(body) == ["stop"]


@pytest.mark.asyncio
async def test_relay_tool_use_ending_maps_to_tool_calls(tmp_path):
    frontier = _ScriptedFrontier(
        [
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"q":"x"}'},
                    }
                ]
            },
            {"finish_reason": "tool_use"},
        ]
    )
    router = _relay_router(tmp_path, frontier)
    body = await _collect(router.stream_openai_chunks(_request()))
    assert "call_abc" in body
    assert _finish_reasons(body) == ["tool_calls"]


class _DyingL3(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="x",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "only "}}
        raise RuntimeError("L3 died mid-stream")


@pytest.mark.asyncio
async def test_midstream_continue_hop_mirrors_upstream_finish_reason(tmp_path):
    """The #2003 L6 continuation hop must not synthesize stop after max_tokens."""
    dying = _DyingL3(base_url="http://l3", default_model="llama3.2:3b")
    frontier = _ScriptedFrontier(["L6-CONTINUE", {"finish_reason": "max_tokens"}])
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=dying,
        ollama_l3=dying,
        ollama_l4=dying,
        ollama_l5=dying,
        metrics=Metrics(),
        stream_fallback_continue=True,
        frontier=frontier,
        frontier_enabled=True,
    )
    body = await _collect(router.stream_openai_chunks(_request("say hello", tier_override="L3")))
    assert frontier.stream_calls == 1
    assert "L6-CONTINUE" in body
    assert _finish_reasons(body) == ["length"]
