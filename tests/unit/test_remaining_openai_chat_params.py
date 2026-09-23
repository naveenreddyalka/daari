"""Remaining OpenAI chat params are declared and forwarded — no silent drops (#1007).

`store`, `metadata`, `prediction`, `modalities`, `audio`, `verbosity`, and
`web_search_options` used to vanish under `extra="ignore"`. `logprobs` / `n`
were parsed but never emitted by `openai_payload()`. Unsupported knobs must
surface without requiring `X-Daari-Meta`.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.openai import ChatCompletionRequest
from daari.gateway.sampling import SamplingParams
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import MOCK_MODEL_CONTENT


REMAINING = {
    "store": True,
    "metadata": {"user_id": "u1", "session": "s1"},
    "prediction": {"type": "content", "content": "hello"},
    "modalities": ["text", "audio"],
    "audio": {"voice": "alloy", "format": "wav"},
    "verbosity": "high",
    "web_search_options": {"search_context_size": "medium"},
    "logprobs": True,
    "n": 2,
}


class TestHttpModelRetention:
    def test_chat_completion_request_keeps_remaining_params(self):
        body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            **REMAINING,
        }
        req = ChatCompletionRequest.model_validate(body)
        assert req.store is True
        assert req.metadata == {"user_id": "u1", "session": "s1"}
        assert req.prediction == {"type": "content", "content": "hello"}
        assert req.modalities == ["text", "audio"]
        assert req.audio == {"voice": "alloy", "format": "wav"}
        assert req.verbosity == "high"
        assert req.web_search_options == {"search_context_size": "medium"}
        assert req.logprobs is True
        assert req.n == 2

    def test_from_openai_body_retains_params(self):
        params = SamplingParams.from_openai_body(REMAINING)
        assert params.store is True
        assert params.metadata == {"user_id": "u1", "session": "s1"}
        assert params.prediction == {"type": "content", "content": "hello"}
        assert params.modalities == ["text", "audio"]
        assert params.audio == {"voice": "alloy", "format": "wav"}
        assert params.verbosity == "high"
        assert params.web_search_options == {"search_context_size": "medium"}
        assert params.logprobs is True
        assert params.n == 2


class TestOpenAIPayloadEmission:
    def test_openai_payload_emits_each_param(self):
        params = SamplingParams.from_openai_body(REMAINING)
        payload = params.openai_payload()
        assert payload["store"] is True
        assert payload["metadata"] == {"user_id": "u1", "session": "s1"}
        assert payload["prediction"] == {"type": "content", "content": "hello"}
        assert payload["modalities"] == ["text", "audio"]
        assert payload["audio"] == {"voice": "alloy", "format": "wav"}
        assert payload["verbosity"] == "high"
        assert payload["web_search_options"] == {"search_context_size": "medium"}
        assert payload["logprobs"] is True
        assert payload["n"] == 2

    def test_unset_remaining_params_are_absent(self):
        payload = SamplingParams().openai_payload()
        for key in (
            "store",
            "metadata",
            "prediction",
            "modalities",
            "audio",
            "verbosity",
            "web_search_options",
            "logprobs",
            "n",
        ):
            assert key not in payload


class TestLoudWarningWithoutMetaHeader:
    @pytest.mark.asyncio
    async def test_unsupported_param_sets_x_daari_warning_header(
        self, settings, tmp_path, monkeypatch
    ):
        """Stock SDKs never send X-Daari-Meta; the header must still warn."""
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            bodies.append(_json.loads(request.content))
            return httpx.Response(
                200, json={"message": {"content": MOCK_MODEL_CONTENT}}
            )

        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.routing.max_tier_for_chat = "L3"
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        asgi = ASGITransport(app=app)
        async with AsyncClient(transport=asgi, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": "hello there"}],
                    "logprobs": True,
                    "store": True,
                },
                # Intentionally no X-Daari-Meta — warning must not need it.
            )

        assert response.status_code == 200
        assert "daari_meta" not in response.json()
        warning = response.headers.get("x-daari-warning") or response.headers.get(
            "X-Daari-Warning"
        )
        assert warning is not None
        assert "logprobs" in warning
        assert "store" in warning
