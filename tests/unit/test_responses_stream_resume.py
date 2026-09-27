"""Responses SSE sequence_number + stream resume (#1139, #1151)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest
from daari.gateway.responses import _replay_events_from_stored, _sse_with_sequence
from daari.gateway.response_store import ResponseStore
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event_name = line.split(" ", 1)[1]
        elif line.startswith("data: ") and event_name:
            events.append((event_name, json.loads(line.split(" ", 1)[1])))
            event_name = None
    return events


def test_sse_with_sequence_embeds_sequence_number():
    frame = _sse_with_sequence(3, "response.created", {"type": "response.created"})
    assert "event: response.created\n" in frame
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload["sequence_number"] == 3
    assert payload["type"] == "response.created"


def test_replay_events_from_stored_message_and_tool():
    stored = {
        "id": "resp_1",
        "object": "response",
        "model": "llama3.2:3b",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "hi", "annotations": []}],
            },
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"q":"x"}',
                "status": "completed",
            },
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    frames = list(_replay_events_from_stored(stored, starting_after=None))
    parsed = _parse_sse("".join(frames))
    names = [name for name, _ in parsed]
    assert names[0] == "response.created"
    assert names[-1] == "response.completed"
    assert "response.output_item.added" in names
    assert "response.output_item.done" in names
    assert "response.output_text.done" in names
    assert "response.function_call_arguments.done" in names
    seqs = [payload["sequence_number"] for _, payload in parsed]
    assert seqs == list(range(len(seqs)))


def test_replay_starting_after_skips_and_past_end_is_empty():
    stored = {
        "id": "resp_2",
        "object": "response",
        "model": "m",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            }
        ],
    }
    all_frames = list(_replay_events_from_stored(stored, starting_after=None))
    all_parsed = _parse_sse("".join(all_frames))
    mid = all_parsed[2][1]["sequence_number"]
    resumed = _parse_sse("".join(_replay_events_from_stored(stored, starting_after=mid)))
    assert resumed[0][1]["sequence_number"] == mid + 1
    assert all(p["sequence_number"] > mid for _, p in resumed)
    past = list(_replay_events_from_stored(stored, starting_after=10_000))
    assert past == []


def _store(settings) -> ResponseStore:
    from pathlib import Path

    path = Path(settings.trace.path).expanduser().parent / "responses.sqlite3"
    return ResponseStore(path)


@pytest.mark.asyncio
async def test_get_stream_resume_from_store(settings):
    app = _app(settings)
    body = {
        "id": "resp_resume",
        "object": "response",
        "model": "llama3.2:3b",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_x",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "hello", "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    }
    _store(settings).put("resp_resume", body, conversation=[], stored=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        full = await client.get("/v1/responses/resp_resume", params={"stream": "true"})
        mid = await client.get(
            "/v1/responses/resp_resume",
            params={"stream": "true", "starting_after": "2"},
        )
        past = await client.get(
            "/v1/responses/resp_resume",
            params={"stream": "true", "starting_after": "9999"},
        )
        plain = await client.get("/v1/responses/resp_resume")
        missing = await client.get("/v1/responses/nope", params={"stream": "true"})

    assert full.status_code == 200
    assert full.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(full.text)
    assert events[0][0] == "response.created"
    assert events[-1][0] == "response.completed"
    assert len(events) >= 3

    mid_events = _parse_sse(mid.text)
    assert mid_events
    assert all(p["sequence_number"] > 2 for _, p in mid_events)

    assert past.status_code == 200
    assert _parse_sse(past.text) == []

    assert plain.status_code == 200
    assert plain.json()["id"] == "resp_resume"
    assert plain.headers["content-type"].startswith("application/json")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_create_stream_emits_contiguous_sequence_numbers(settings):
    app = _app(settings)

    async def fake_chunks(request: InternalRequest):
        for piece in ("Hello", " world"):
            chunk = {"choices": [{"delta": {"content": piece}}]}
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_chunks
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses", json={"model": "daari", "input": "say hi", "stream": True}
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "response.created"
    assert events[-1][0] == "response.completed"
    seqs = [payload["sequence_number"] for _, payload in events]
    assert seqs == list(range(len(seqs)))
    assert events[-1][1]["sequence_number"] == len(seqs) - 1
    assert all("sequence_number" in payload for _, payload in events)


@pytest.mark.asyncio
async def test_get_stream_in_flight_background_returns_409(settings):
    app = _app(settings)
    _store(settings).put(
        "resp_bg",
        {
            "id": "resp_bg",
            "object": "response",
            "model": "m",
            "status": "queued",
            "output": [],
        },
        conversation=[],
        stored=True,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/responses/resp_bg", params={"stream": "true"})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "completed" in str(detail).lower() or "terminal" in str(detail).lower()
