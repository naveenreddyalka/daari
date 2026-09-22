"""Unit tests for gateway streaming keepalive (#276, #972)."""

from __future__ import annotations

import asyncio

import pytest

from daari.gateway.streaming import (
    NDJSON_KEEPALIVE_FRAME,
    SSE_IDLE_ERROR_FRAME,
    SSE_KEEPALIVE_FRAME,
    stream_with_keepalive,
)


async def _collect(source) -> list[str]:
    return [chunk async for chunk in source]


async def _delayed_chunks(delay: float, *chunks: str):
    await asyncio.sleep(delay)
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_keepalive_before_first_chunk():
    body = await _collect(
        stream_with_keepalive(
            _delayed_chunks(0.05, "data: hello\n\n"),
            interval_seconds=0.01,
        )
    )
    assert SSE_KEEPALIVE_FRAME in body
    keepalive_index = body.index(SSE_KEEPALIVE_FRAME)
    data_index = next(i for i, part in enumerate(body) if part.startswith("data:"))
    assert keepalive_index < data_index


@pytest.mark.asyncio
async def test_keepalive_mid_stream_after_first_chunk():
    """Heartbeats continue for the whole stream, not only TTFT (#972)."""

    async def gap_after_first():
        yield "first\n"
        await asyncio.sleep(0.05)
        yield "second\n"

    body = await _collect(stream_with_keepalive(gap_after_first(), interval_seconds=0.01))
    assert body[0] == "first\n"
    assert body[-1] == "second\n"
    assert SSE_KEEPALIVE_FRAME in body[1:-1]


@pytest.mark.asyncio
async def test_disabled_when_interval_zero():
    body = await _collect(
        stream_with_keepalive(
            _delayed_chunks(0.05, "data: hello\n\n"),
            interval_seconds=0,
        )
    )
    assert SSE_KEEPALIVE_FRAME not in body
    assert body == ["data: hello\n\n"]


@pytest.mark.asyncio
async def test_ndjson_keepalive_frame():
    body = await _collect(
        stream_with_keepalive(
            _delayed_chunks(0.05, '{"done": false}\n'),
            interval_seconds=0.01,
            frame=NDJSON_KEEPALIVE_FRAME,
        )
    )
    assert NDJSON_KEEPALIVE_FRAME in body


@pytest.mark.asyncio
async def test_idle_timeout_emits_in_band_error_then_stops():
    async def hang_after_first():
        yield "first\n"
        await asyncio.sleep(1.0)
        yield "never\n"

    body = await _collect(
        stream_with_keepalive(
            hang_after_first(),
            interval_seconds=0.01,
            idle_timeout_seconds=0.05,
        )
    )
    assert body[0] == "first\n"
    assert body[-1] == SSE_IDLE_ERROR_FRAME
    assert "never\n" not in body
    assert "stream_idle_timeout" in body[-1]


async def _raising_after_first():
    yield "first\n"
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_propagates_upstream_exception():
    with pytest.raises(RuntimeError, match="boom"):
        await _collect(stream_with_keepalive(_raising_after_first(), interval_seconds=0.01))
