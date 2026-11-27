"""Responses status incomplete + incomplete_details from finish_reason (#2332)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.responses import (
    _incomplete_details_from_finish_reason,
    _response_body,
    _status_from_result,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def _result(*, finish_reason: str | None, content: str = "partial") -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        finish_reason=finish_reason,
        daari_meta=DaariMeta(tier="L4", executor="ollama"),
    )


def test_incomplete_details_maps_length_and_content_filter() -> None:
    assert _incomplete_details_from_finish_reason("length") == {"reason": "max_output_tokens"}
    assert _incomplete_details_from_finish_reason("max_tokens") == {"reason": "max_output_tokens"}
    assert _incomplete_details_from_finish_reason("content_filter") == {"reason": "content_filter"}
    assert _incomplete_details_from_finish_reason("refusal") == {"reason": "content_filter"}
    assert _incomplete_details_from_finish_reason("stop") is None
    assert _incomplete_details_from_finish_reason("tool_calls") is None
    assert _incomplete_details_from_finish_reason(None) is None


def test_status_from_result_incomplete_for_length() -> None:
    status, details = _status_from_result(_result(finish_reason="length"))
    assert status == "incomplete"
    assert details == {"reason": "max_output_tokens"}


def test_status_from_result_completed_for_stop() -> None:
    status, details = _status_from_result(_result(finish_reason="stop"))
    assert status == "completed"
    assert details is None


def test_response_body_incomplete_keeps_partial_output() -> None:
    status, details = _status_from_result(_result(finish_reason="length", content="cut off"))
    body = _response_body(
        "resp_test",
        _result(finish_reason="length", content="cut off"),
        input_chars=12,
        include_daari_meta=False,
        status=status,
        incomplete_details=details,
    )
    assert body["status"] == "incomplete"
    assert body["incomplete_details"] == {"reason": "max_output_tokens"}
    assert body["output"]  # partial output retained
    assert "cut off" in str(body["output"])


def test_response_body_completed_unchanged_shape() -> None:
    body = _response_body(
        "resp_ok",
        _result(finish_reason="stop", content="hello"),
        input_chars=4,
        include_daari_meta=False,
        status="completed",
    )
    assert body["status"] == "completed"
    assert "incomplete_details" not in body
    assert body["output"]


@pytest.mark.asyncio
async def test_post_responses_length_is_incomplete(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="cut",
            model="m",
            finish_reason="length",
            daari_meta=DaariMeta(tier="L4", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/responses", json={"model": "daari", "input": "hi"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "incomplete"
        assert body["incomplete_details"] == {"reason": "max_output_tokens"}
        assert body["output"]
        rid = body["id"]
        replay = await client.get(f"/v1/responses/{rid}")
        assert replay.status_code == 200
        assert replay.json()["status"] == "incomplete"
        assert replay.json()["incomplete_details"] == {"reason": "max_output_tokens"}


@pytest.mark.asyncio
async def test_post_responses_refusal_is_content_filter(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="",
            model="m",
            finish_reason="refusal",
            daari_meta=DaariMeta(tier="L6", executor="openai", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/responses", json={"model": "daari", "input": "hi"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "incomplete"
        assert body["incomplete_details"] == {"reason": "content_filter"}


@pytest.mark.asyncio
async def test_stream_responses_emits_incomplete_event(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_stream(request: InternalRequest):
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_stream
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/v1/responses",
            json={"model": "daari", "input": "hi", "stream": True},
        ) as resp:
            assert resp.status_code == 200
            text = "".join([chunk async for chunk in resp.aiter_text()])
    assert "response.incomplete" in text
    assert "max_output_tokens" in text
    assert "response.completed" not in text
    # Stored body is replayable via the incomplete event payload.
    frames = [line for line in text.splitlines() if line.startswith("data:")]
    terminal = json.loads(frames[-1].removeprefix("data: ").strip())
    assert terminal["type"] == "response.incomplete"
    assert terminal["response"]["status"] == "incomplete"
