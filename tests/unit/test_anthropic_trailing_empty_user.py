"""Keep a trailing empty user turn on Anthropic Messages ingress (#1768)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "", []])
async def test_trailing_empty_user_turn_is_kept(settings, content) -> None:
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_route(request: InternalRequest):
        seen.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [
                    {"role": "user", "content": "start"},
                    {"role": "user", "content": ""},
                    {"role": "assistant", "content": "working"},
                    {"role": "user", "content": content},
                ],
            },
        )
    assert response.status_code == 200
    assert seen
    last = seen[0].messages[-1]
    assert last.role == "user"
    assert last.content == ""
    roles = [message.role for message in seen[0].messages]
    assert roles == ["user", "assistant", "user"]
    outbound = to_anthropic_payload(seen[0], model="claude")
    assert outbound["messages"][-1]["role"] == "user"
    assert outbound["messages"][-1]["content"] == ""
