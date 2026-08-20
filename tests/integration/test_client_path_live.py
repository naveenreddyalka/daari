"""Client-path live E2E pack against real Ollama (issue #191).

The existing live tests cover one chat path (`test_ollama_live.py`) and
sampling (`test_sampling_live.py`: `max_tokens` binds, seed reproduces).
This module is the rest of what an IDE client actually sends: OpenAI and
Anthropic streaming, vision, and embeddings. Assertions are on observable
behavior, not mocked payloads.

Skipped unless `OLLAMA_HOST` is set. The vision color check additionally
skips when no vision-capable model is pulled (llama3.2-vision, llava, …);
the 422 on a text-only stack always runs.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import zlib

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS

OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
CHAT_MODEL = "llama3.2:3b"
EMBED_MODEL = "nomic-embed-text"


def _solid_png(*, width: int = 16, height: int = 16, rgb: tuple[int, int, int] = (255, 0, 0)) -> str:
    """A real RGB PNG — not a 1×1 stub — so a vision model can name the color."""
    red, green, blue = rgb
    raw = b"".join(b"\x00" + bytes([red, green, blue]) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")


_RED_PNG = _solid_png()
_VISION_MODEL_MARKERS = (
    "vision",
    "llava",
    "moondream",
    "bakllava",
    "minicpm-v",
    "qwen2.5vl",
    "qwen2-vl",
    "pixtral",
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not OLLAMA_HOST, reason="Set OLLAMA_HOST to run live Ollama tests"),
]


def _live_settings(tmp_path, *, vision_model: str | None = None):
    from daari.config.settings import Settings

    models = {"l3": CHAT_MODEL, "l4": CHAT_MODEL, "l5": CHAT_MODEL}
    # Empty capabilities fall back to stock defaults that tag L5 as vision —
    # even when L5 is a text-only 3B. Declare the catalog explicitly so a
    # text-only stack is actually text-only.
    capabilities: dict[str, list[str]] = {
        CHAT_MODEL: ["tools"],
    }
    if vision_model:
        models["l3"] = vision_model
        capabilities[vision_model] = ["vision"]
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": models["l3"], "l4": models["l4"], "l5": models["l5"], "capabilities": capabilities},
            "ollama": {"base_url": OLLAMA_HOST or "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": False},
                "l1": {"enabled": True, "path": str(tmp_path / "l1"), "embedding_model": EMBED_MODEL},
            },
            "context": {"enabled": False, "path": str(tmp_path / "context")},
            "routing": {"max_tier_for_chat": "L3"},
            "frontier": {"enabled": False},
        }
    )


def _app(tmp_path, *, vision_model: str | None = None):
    settings = _live_settings(tmp_path, vision_model=vision_model)
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _pulled_models() -> list[str]:
    try:
        tags = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5).json()
    except Exception:
        return []
    return [item.get("name", "") for item in tags.get("models", [])]


def _vision_model() -> str | None:
    for name in _pulled_models():
        lowered = name.lower()
        if any(marker in lowered for marker in _VISION_MODEL_MARKERS):
            return name
    return None


def _openai_stream_contents(body: str) -> list[str]:
    parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        payload = json.loads(line[len("data: ") :])
        for choice in payload.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("content"):
                parts.append(delta["content"])
    return parts


def _anthropic_text_deltas(body: str) -> list[str]:
    deltas: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("type") == "content_block_delta":
            delta = payload.get("delta") or {}
            if delta.get("text"):
                deltas.append(delta["text"])
    return deltas


@pytest.mark.asyncio
async def test_openai_stream_yields_multiple_chunks(tmp_path):
    app = _app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": "Count from one to five in words."}],
                "stream": True,
                "max_tokens": 40,
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    parts = _openai_stream_contents(response.text)
    assert len(parts) > 1, f"expected more than one content chunk, got {parts!r}"
    assert "".join(parts).strip()


@pytest.mark.asyncio
async def test_anthropic_stream_yields_multiple_deltas(tmp_path):
    app = _app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Count from one to five in words."}],
                "stream": True,
                "max_tokens": 40,
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert "event: message_start" in response.text
    assert "event: message_stop" in response.text
    deltas = _anthropic_text_deltas(response.text)
    assert len(deltas) > 1, f"expected more than one text delta, got {deltas!r}"
    assert "".join(deltas).strip()


@pytest.mark.asyncio
async def test_vision_on_text_only_stack_returns_422(tmp_path):
    app = _app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "what color?"},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{_RED_PNG}"},
                            },
                        ],
                    }
                ],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 422, response.text
    assert "vision" in response.text.lower()


@pytest.mark.asyncio
async def test_vision_image_conditions_the_answer(tmp_path):
    model = _vision_model()
    if model is None:
        pytest.skip(
            "no vision-capable Ollama model pulled "
            "(llama3.2-vision, llava, moondream, …)"
        )
    app = _app(tmp_path, vision_model=model)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Reply with only the color of this image."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{_RED_PNG}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 16,
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    text = response.json()["choices"][0]["message"]["content"].lower()
    assert "red" in text, f"vision model should see the red PNG, got {text!r}"


@pytest.mark.asyncio
async def test_embeddings_vector_length_matches_embedder(tmp_path):
    raw = httpx.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": "hello"},
        timeout=60.0,
    )
    raw.raise_for_status()
    expected = len(raw.json()["embedding"])
    assert expected > 0

    app = _app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": EMBED_MODEL, "input": "hello"},
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    body = response.json()
    vector = body["data"][0]["embedding"]
    assert len(vector) == expected
    assert body["model"] == EMBED_MODEL
    assert all(isinstance(value, float) for value in vector[:8])
