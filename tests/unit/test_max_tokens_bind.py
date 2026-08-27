"""G5: max_tokens live check binds on usage + finish_reason, not the word twenty."""

from daari.gateway.sampling import max_tokens_held


def test_max_tokens_held_accepts_truncated_body_even_if_text_says_twenty():
    body = {
        "usage": {"completion_tokens": 8},
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "one two three twenty"},
            }
        ],
    }
    assert max_tokens_held(body, 8) is True


def test_max_tokens_held_rejects_over_cap():
    body = {
        "usage": {"completion_tokens": 20},
        "choices": [{"finish_reason": "stop", "message": {"content": "one"}}],
    }
    assert max_tokens_held(body, 8) is False


def test_max_tokens_held_rejects_missing_usage():
    body = {"choices": [{"finish_reason": "length", "message": {"content": "x"}}]}
    assert max_tokens_held(body, 8) is False
