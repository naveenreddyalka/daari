"""Live Anthropic Messages API egress — skipped unless ANTHROPIC_API_KEY is set."""

from __future__ import annotations

import os

import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.frontier import FrontierExecutor

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not ANTHROPIC_API_KEY, reason="Set ANTHROPIC_API_KEY to run live Anthropic egress tests"
    ),
]


@pytest.mark.asyncio
async def test_native_messages_round_trip():
    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-3-5-haiku-latest",
        api_key=ANTHROPIC_API_KEY,
        provider="anthropic",
        timeout=60.0,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="Reply with the single word: pong")],
        model="claude-3-5-haiku-latest",
    )
    request.sampling.max_tokens = 16
    response = await executor.execute(request, escalated_from="L3", local_confidence=0.1)
    assert "pong" in response.content.lower()
    assert response.daari_meta.usage_estimated is False
    assert (response.daari_meta.output_tokens or 0) > 0
