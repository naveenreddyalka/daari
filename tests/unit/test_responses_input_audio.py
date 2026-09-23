"""Responses API preserves OpenAI input_audio parts (#997)."""

from __future__ import annotations

import base64

from daari.gateway.responses import ResponsesRequest, responses_input_to_messages

TINY_WAV = base64.b64encode(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 8).decode()


def test_responses_message_keeps_input_audio() -> None:
    body = ResponsesRequest(
        model="daari",
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "what did I say?"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": TINY_WAV, "format": "wav"},
                    },
                ],
            }
        ],
    )
    messages = responses_input_to_messages(body)
    assert len(messages) == 1
    assert messages[0].content == "what did I say?"
    assert len(messages[0].audio) == 1
    assert messages[0].audio[0].data == TINY_WAV
    assert messages[0].audio[0].format == "wav"


def test_responses_text_only_has_no_audio() -> None:
    body = ResponsesRequest(model="daari", input="hello")
    messages = responses_input_to_messages(body)
    assert messages[0].audio == []


def test_responses_audio_rebuilds_on_l6_payload() -> None:
    from daari.gateway.internal import InternalRequest
    from daari.router.frontier import FrontierExecutor

    body = ResponsesRequest(
        model="daari",
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "transcribe"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": TINY_WAV, "format": "wav"},
                    },
                ],
            }
        ],
    )
    req = InternalRequest(messages=responses_input_to_messages(body), model="gpt-4o")
    content = FrontierExecutor(
        base_url="http://t", default_model="gpt-4o", api_key="sk"
    )._build_messages(req)[0]["content"]
    assert isinstance(content, list)
    audio_parts = [p for p in content if p.get("type") == "input_audio"]
    assert len(audio_parts) == 1
    assert audio_parts[0]["input_audio"]["data"] == TINY_WAV
