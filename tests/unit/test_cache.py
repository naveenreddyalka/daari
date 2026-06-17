from __future__ import annotations

from daari.cache.exact import cache_key
from daari.gateway.internal import InternalRequest, Message, RequestMeta


class TestCacheKey:
    def test_temperature_affects_key(self):
        base = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
        )
        warm = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
            temperature=0.9,
        )
        assert cache_key(base) != cache_key(warm)

    def test_tier_override_affects_key(self):
        plain = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
        )
        override = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
            meta=RequestMeta(tier_override="L3"),
        )
        assert cache_key(plain) != cache_key(override)

    def test_tool_calls_in_messages_affect_key(self):
        plain = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
        )
        with_tools = InternalRequest(
            messages=[
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[{"id": "1", "type": "function", "function": {"name": "x"}}],
                ),
                Message(role="user", content="result"),
            ],
            model="llama3.2:3b",
        )
        assert cache_key(plain) != cache_key(with_tools)
