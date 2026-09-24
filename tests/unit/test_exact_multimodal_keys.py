"""ExactCache L0 keys must differentiate multimodal tokens (#1040)."""

from __future__ import annotations

from daari.cache.exact import cache_key
from daari.gateway.internal import ContentAudio, ContentImage, InternalRequest, Message


def _text(caption: str = "what is this?") -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=caption)],
        model="llama3.2:3b",
    )


def _with_image(caption: str, data: str) -> InternalRequest:
    return InternalRequest(
        messages=[
            Message(
                role="user",
                content=caption,
                images=[ContentImage(data=data, media_type="image/png")],
            )
        ],
        model="llama3.2:3b",
    )


def _with_audio(caption: str, data: str) -> InternalRequest:
    return InternalRequest(
        messages=[
            Message(
                role="user",
                content=caption,
                audio=[ContentAudio(data=data, format="wav")],
            )
        ],
        model="llama3.2:3b",
    )


def test_cache_key_differs_for_distinct_images() -> None:
    caption = "what is in this picture?"
    key_a = cache_key(_with_image(caption, "img-a"))
    key_b = cache_key(_with_image(caption, "img-b"))
    assert key_a != key_b
    assert key_a == cache_key(_with_image(caption, "img-a"))


def test_cache_key_differs_for_distinct_audio_clips() -> None:
    caption = "what did I say?"
    key_a = cache_key(_with_audio(caption, "clip-a"))
    key_b = cache_key(_with_audio(caption, "clip-b"))
    assert key_a != key_b
    assert key_a == cache_key(_with_audio(caption, "clip-a"))


def test_cache_key_text_only_matches_no_media_request() -> None:
    plain = _text("hello")
    assert cache_key(plain) == cache_key(_text("hello"))
    assert cache_key(plain) != cache_key(_with_image("hello", "img-a"))
    assert cache_key(plain) != cache_key(_with_audio("hello", "clip-a"))
