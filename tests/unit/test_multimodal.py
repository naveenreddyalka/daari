"""Image parts must reach the model or fail loudly (issue #164).

A vision request used to be flattened to text, so the model answered as if no
image was sent and `required_capabilities` never saw `vision`. These tests pin
the opposite: images survive the gateway, split the cache, ride the Ollama and
frontier payloads, and a text-only stack returns 422 rather than a confident
wrong answer.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import cache_key
from daari.gateway.content import content_to_text, extract_images
from daari.gateway.internal import ContentImage, InternalRequest, Message
from daari.router.capabilities import required_capabilities
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext, OllamaExecutor
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT

# 1×1 PNG. Any vision model can ingest it; we never decode it in these tests.
TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
DATA_URL = f"data:image/png;base64,{TINY_PNG}"


def _vision_blocks(text: str = "what is in this image?"):
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": DATA_URL}},
    ]


class TestExtractImages:
    def test_openai_image_url_is_kept(self):
        images = extract_images(_vision_blocks())
        assert len(images) == 1
        assert images[0].data == TINY_PNG
        assert images[0].media_type == "image/png"

    def test_anthropic_base64_source_is_kept(self):
        blocks = [
            {"type": "text", "text": "describe"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": TINY_PNG},
            },
        ]
        images = extract_images(blocks)
        assert images[0].data == TINY_PNG
        assert images[0].media_type == "image/jpeg"

    def test_text_only_content_has_no_images(self):
        assert extract_images("just text") == []
        assert extract_images([{"type": "text", "text": "hi"}]) == []

    def test_content_to_text_still_returns_the_caption(self):
        """Flattening text is fine; dropping the image from Message is not."""
        assert content_to_text(_vision_blocks("caption")) == "caption"


class TestVisionCapability:
    def test_images_on_the_message_require_vision(self):
        req = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="what is this?",
                    images=[ContentImage(data=TINY_PNG, media_type="image/png")],
                )
            ],
            model="daari",
        )
        assert "vision" in required_capabilities(req)

    def test_a_text_prompt_that_mentions_image_url_does_not(self):
        """The old detector matched the substring in already-flattened text."""
        req = InternalRequest(
            messages=[Message(role="user", content="please fetch image_url later")],
            model="daari",
        )
        assert "vision" not in required_capabilities(req)


class TestCacheKey:
    def _request(self, data: str) -> InternalRequest:
        return InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="what is this?",
                    images=[ContentImage(data=data, media_type="image/png")],
                )
            ],
            model="daari",
        )

    def test_different_images_do_not_share_a_cache_key(self):
        assert cache_key(self._request(TINY_PNG)) != cache_key(self._request(TINY_PNG + "xx"))

    def test_identical_images_share_a_cache_key(self):
        assert cache_key(self._request(TINY_PNG)) == cache_key(self._request(TINY_PNG))

    def test_a_text_only_request_keeps_its_pre_164_key(self):
        plain = InternalRequest(
            messages=[Message(role="user", content="what is this?")], model="daari"
        )
        with_empty = InternalRequest(
            messages=[Message(role="user", content="what is this?", images=[])],
            model="daari",
        )
        assert cache_key(plain) == cache_key(with_empty)


class TestOllamaPayload:
    def test_images_land_on_the_ollama_message(self):
        req = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="what is this?",
                    images=[ContentImage(data=TINY_PNG, media_type="image/png")],
                )
            ],
            model="llama3.2:3b",
        )
        payload = OllamaExecutor(base_url="http://t", default_model="m")._payload(
            req, "m", stream=False
        )
        assert payload["messages"][0]["images"] == [TINY_PNG]
        assert "images" not in payload["messages"][0] or isinstance(
            payload["messages"][0]["images"][0], str
        )


class TestFrontierPayload:
    def test_images_become_openai_image_url_parts(self):
        req = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="what is this?",
                    images=[ContentImage(data=TINY_PNG, media_type="image/png")],
                )
            ],
            model="gpt-4o",
        )
        messages = FrontierExecutor(
            base_url="http://t", default_model="gpt-4o", api_key="sk"
        )._build_messages(req)
        content = messages[0]["content"]
        assert isinstance(content, list)
        types = [part["type"] for part in content]
        assert "text" in types
        assert "image_url" in types
        url = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")
        assert url.startswith("data:image/png;base64,")
        assert TINY_PNG in url


def _recording_transport(content: str = MOCK_MODEL_CONTENT):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        bodies.append(_json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": content}})

    return httpx.MockTransport(handler), bodies


def _patch_transport(monkeypatch, transport):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _app(settings, *, vision: bool):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    settings.models.capabilities = {
        settings.models.l3: ["vision", "tools"] if vision else ["tools"],
        settings.models.l4: ["tools"],
        settings.models.l5: ["tools"],
    }
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


class TestGateway:
    @pytest.mark.asyncio
    async def test_openai_vision_request_reaches_ollama(self, settings, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        app = _app(settings, vision=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": _vision_blocks()}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert bodies[0]["messages"][0]["images"] == [TINY_PNG]

    @pytest.mark.asyncio
    async def test_text_only_stack_returns_422(self, settings, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        app = _app(settings, vision=False)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": _vision_blocks()}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 422, response.text
        assert bodies == [], "a text-only stack must not call the model at all"
        assert "vision" in response.text.lower()

    @pytest.mark.asyncio
    async def test_image_only_user_message_is_not_dropped(self, settings, monkeypatch):
        """No caption, just an image — used to vanish in _to_internal_messages."""
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        app = _app(settings, vision=True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "image_url", "image_url": {"url": DATA_URL}}],
                        }
                    ],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert bodies[0]["messages"][0]["images"] == [TINY_PNG]
