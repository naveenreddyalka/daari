"""Unit tests for gateway streaming keepalive (#276)."""

from __future__ import annotations

import asyncio

import pytest

from daari.gateway.streaming import (
    NDJSON_KEEPALIVE_FRAME,
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
async def test_no_keepalive_after_first_chunk():
    async def gap_after_first():
        yield "first\n"
        await asyncio.sleep(0.05)
        yield "second\n"

    body = await _collect(stream_with_keepalive(gap_after_first(), interval_seconds=0.01))
    assert body == ["first\n", "second\n"]


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


async def _raising_after_first():
    yield "first\n"
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_propagates_upstream_exception():
    with pytest.raises(RuntimeError, match="boom"):
        await _collect(stream_with_keepalive(_raising_after_first(), interval_seconds=0.01))
