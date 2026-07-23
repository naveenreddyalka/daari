"""MLX backend executor + wiring (issue #97)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message
from daari.router.mlx_executor import MLXExecutor, MLXRequestError
from daari.router.router import AppContext, OllamaExecutor


def _patch_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.mlx_executor.httpx.AsyncClient", patched_client)


class TestPayload:
    def _executor(self) -> MLXExecutor:
        return MLXExecutor(base_url="http://test", default_model="mlx-model")

    def test_openai_shape_with_string_tool_arguments(self):
        request = InternalRequest(
            model="mlx-model",
            messages=[
                Message(role="user", content="read it"),
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": {"path": "a.py"}},
                        }
                    ],
                ),
            ],
        )
        payload = self._executor()._payload(request, "mlx-model", stream=False)
        args = payload["messages"][1]["tool_calls"][0]["function"]["arguments"]
        assert args == json.dumps({"path": "a.py"}), "OpenAI wire wants JSON-string args"

    def test_contentless_messages_dropped(self):
        request = InternalRequest(
            model="mlx-model",
            messages=[
                Message(role="assistant", content=None),
                Message(role="user", content="hello"),
            ],
        )
        payload = self._executor()._payload(request, "mlx-model", stream=False)
        assert [m["role"] for m in payload["messages"]] == ["user"]

    def test_tools_and_temperature_forwarded(self):
        request = InternalRequest(
            model="mlx-model",
            temperature=0.2,
            messages=[Message(role="user", content="hi")],
            tools=[{"type": "function", "function": {"name": "t"}}],
        )
        payload = self._executor()._payload(request, "mlx-model", stream=True)
        assert payload["tools"][0]["function"]["name"] == "t"
        assert payload["temperature"] == 0.2
        assert payload["stream"] is True


@pytest.mark.asyncio
async def test_execute_parses_openai_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "from-mlx"}, "finish_reason": "stop"}
                ]
            },
        )

    _patch_client(monkeypatch, handler)
    executor = MLXExecutor(base_url="http://test", default_model="mlx-model", tier="L3")
    response = await executor.execute(
        InternalRequest(model="mlx-model", messages=[Message(role="user", content="hi")])
    )
    assert response.content == "from-mlx"
    assert response.daari_meta.executor == "mlx"
    assert response.daari_meta.provider_id == "mlx:l3"


@pytest.mark.asyncio
async def test_execute_error_includes_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model not loaded"})

    _patch_client(monkeypatch, handler)
    executor = MLXExecutor(base_url="http://test", default_model="mlx-model")
    with pytest.raises(MLXRequestError) as excinfo:
        await executor.execute(
            InternalRequest(model="mlx-model", messages=[Message(role="user", content="hi")])
        )
    assert excinfo.value.status_code == 500
    assert "model not loaded" in str(excinfo.value)


@pytest.mark.asyncio
async def test_stream_converts_sse_to_ollama_events(monkeypatch):
    sse_body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    _patch_client(monkeypatch, handler)
    executor = MLXExecutor(base_url="http://test", default_model="mlx-model")
    events = [
        e
        async for e in executor.stream(
            InternalRequest(model="mlx-model", messages=[Message(role="user", content="hi")])
        )
    ]
    texts = [e["message"]["content"] for e in events if not e["done"]]
    assert "".join(texts) == "Hello"
    assert events[-1]["done"] is True


@pytest.mark.asyncio
async def test_stream_forwards_tool_call_deltas(monkeypatch):
    sse_body = (
        'data: {"choices":[{"delta":{"tool_calls":[{"id":"t1","function":{"name":"read_file","arguments":"{}"}}]}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    _patch_client(monkeypatch, handler)
    executor = MLXExecutor(base_url="http://test", default_model="mlx-model")
    events = [
        e
        async for e in executor.stream(
            InternalRequest(model="mlx-model", messages=[Message(role="user", content="go")])
        )
    ]
    tool_events = [e for e in events if e["message"].get("tool_calls")]
    assert tool_events[0]["message"]["tool_calls"][0]["function"]["name"] == "read_file"


@pytest.mark.asyncio
async def test_stream_error_includes_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "unknown model"})

    _patch_client(monkeypatch, handler)
    executor = MLXExecutor(base_url="http://test", default_model="mlx-model")
    with pytest.raises(MLXRequestError) as excinfo:
        async for _ in executor.stream(
            InternalRequest(model="mlx-model", messages=[Message(role="user", content="hi")])
        ):
            pass
    assert "unknown model" in str(excinfo.value)


class TestSettingsWiring:
    def test_mlx_disabled_by_default(self):
        settings = Settings()
        assert settings.mlx.enabled is False
        assert settings.mlx.base_url == "http://127.0.0.1:11440"
        assert settings.mlx.models == {}

    def test_mapped_tier_gets_mlx_executor(self, settings):
        settings.mlx.enabled = True
        settings.mlx.models = {"L3": "mlx-community/Llama-3.2-3B-Instruct-4bit"}
        ctx = AppContext.from_settings(settings)
        assert isinstance(ctx.router.ollama_l3, MLXExecutor)
        assert ctx.router.ollama_l3.default_model == "mlx-community/Llama-3.2-3B-Instruct-4bit"
        assert isinstance(ctx.router.ollama_l4, OllamaExecutor)
        assert isinstance(ctx.router.ollama_l5, OllamaExecutor)

    def test_disabled_mlx_keeps_ollama_everywhere(self, settings):
        settings.mlx.enabled = False
        settings.mlx.models = {"L3": "mlx-community/whatever"}
        ctx = AppContext.from_settings(settings)
        assert isinstance(ctx.router.ollama_l3, OllamaExecutor)


class TestDoctor:
    def test_disabled_check_passes(self, settings):
        from daari.setup.doctor import _check_mlx

        result = _check_mlx(settings, None)
        assert result.ok and result.optional and "disabled" in result.detail

    def test_enabled_without_models_fails(self, settings):
        from daari.setup.doctor import _check_mlx

        settings.mlx.enabled = True
        result = _check_mlx(settings, None)
        assert not result.ok and "maps no tiers" in result.detail

    def test_reachable_server_reports_tiers(self, settings):
        from daari.setup.doctor import _check_mlx

        settings.mlx.enabled = True
        settings.mlx.models = {"L3": "m"}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = _check_mlx(settings, client)
        assert result.ok and "tiers: L3" in result.detail

    def test_unreachable_server_suggests_start_command(self, settings):
        from daari.setup.doctor import _check_mlx

        settings.mlx.enabled = True
        settings.mlx.models = {"L3": "m"}

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = _check_mlx(settings, client)
        assert not result.ok and "mlx_lm.server" in result.detail
