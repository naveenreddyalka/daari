"""Hoist trailing system only on local Ollama; preserve on Anthropic egress (#1154)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import hoist_system_messages
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.router import AppContext, OllamaExecutor
from daari.server.app import create_app

DOC = Path(__file__).resolve().parents[2] / "docs/developer/concepts/clients-and-gateways.md"


def test_docs_mention_hoist_local_only():
    text = DOC.read_text(encoding="utf-8")
    assert "hoist" in text.lower() or "mid-conversation system" in text.lower()


def test_ollama_payload_hoists_trailing_system():
    executor = OllamaExecutor(base_url="http://127.0.0.1:9", default_model="m", tier="L3")
    request = InternalRequest(
        messages=[
            Message(role="system", content="base"),
            Message(role="user", content="q"),
            Message(role="system", content="hook"),
        ],
        model="m",
    )
    payload = executor._payload(request, "m", stream=False)
    assert [m["role"] for m in payload["messages"]] == ["system", "system", "user"]
    assert payload["messages"][1]["content"] == "hook"


@pytest.mark.asyncio
async def test_messages_gateway_does_not_hoist_before_route(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    seen: dict = {}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        seen["roles"] = [m.role for m in request.messages]
        seen["contents"] = [m.content for m in request.messages]
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 64,
                "system": "base system",
                "messages": [
                    {"role": "user", "content": "question"},
                    {"role": "system", "content": "SessionStart hook"},
                ],
            },
            headers={"X-Daari-Tier-Override": "L6"},
        )
    assert response.status_code == 200
    # top-level system, user, trailing system — not hoisted at gateway
    assert seen["roles"] == ["system", "user", "system"]
    assert seen["contents"][-1] == "SessionStart hook"
    # pure helper still hoists when called directly (local path)
    hoisted = hoist_system_messages(
        [
            Message(role="system", content="base system"),
            Message(role="user", content="question"),
            Message(role="system", content="SessionStart hook"),
        ]
    )
    assert [m.role for m in hoisted] == ["system", "system", "user"]
