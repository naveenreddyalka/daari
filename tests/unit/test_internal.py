from __future__ import annotations

from daari.gateway.internal import InternalRequest, Message


class TestInternalRequest:
    def test_has_tool_calls_in_history_false(self):
        req = InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="llama3.2:3b",
        )
        assert req.has_tool_calls_in_history is False

    def test_has_tool_calls_in_history_true(self):
        req = InternalRequest(
            messages=[
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[{"id": "1", "type": "function"}],
                ),
                Message(role="tool", content="ok"),
            ],
            model="llama3.2:3b",
        )
        assert req.has_tool_calls_in_history is True
