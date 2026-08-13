"""Sampling parameters survive the whole path to the backend (issue #161).

`test_sampling_params.py` covers the mapping in isolation; these assert the values
actually reach the wire, which is the part that was broken. What a model *does*
with `num_predict` or `seed` is the model's business and is covered by
`tests/integration/test_sampling_live.py` against a real Ollama.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import cache_key
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT


def _recording_transport(content: str = "answer"):
    """Capture every JSON body Ollama would have received."""
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


def _app(settings, tmp_path):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


async def _post(app, body):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/chat/completions", json=body, headers=META_HEADERS)


BASE = {"model": "daari", "messages": [{"role": "user", "content": "hello there"}]}


class TestParametersReachOllama:
    @pytest.mark.asyncio
    async def test_max_tokens_becomes_num_predict_on_the_wire(
        self, settings, tmp_path, monkeypatch
    ):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        response = await _post(_app(settings, tmp_path), {**BASE, "max_tokens": 16})

        assert response.status_code == 200
        assert bodies[0]["options"]["num_predict"] == 16

    @pytest.mark.asyncio
    async def test_seed_top_p_and_stop_reach_the_wire(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        await _post(
            _app(settings, tmp_path),
            {**BASE, "seed": 99, "top_p": 0.2, "stop": ["STOP"]},
        )

        options = bodies[0]["options"]
        assert options["seed"] == 99
        assert options["top_p"] == 0.2
        assert options["stop"] == ["STOP"]

    @pytest.mark.asyncio
    async def test_num_ctx_is_still_ours_to_set(self, settings, tmp_path, monkeypatch):
        """Sizing the context window is daari's job, not the client's."""
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        await _post(_app(settings, tmp_path), {**BASE, "max_tokens": 8})

        assert bodies[0]["options"]["num_ctx"] > 0

    @pytest.mark.asyncio
    async def test_json_mode_sets_the_format_field(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport(content='{"ok": true}')
        _patch_transport(monkeypatch, transport)
        await _post(
            _app(settings, tmp_path),
            {**BASE, "response_format": {"type": "json_object"}},
        )

        assert bodies[0]["format"] == "json"

    @pytest.mark.asyncio
    async def test_no_format_field_without_json_mode(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        await _post(_app(settings, tmp_path), BASE)

        assert "format" not in bodies[0]

    @pytest.mark.asyncio
    async def test_a_plain_request_sends_no_sampling_options(
        self, settings, tmp_path, monkeypatch
    ):
        """Absent parameters must not become explicit values."""
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        await _post(_app(settings, tmp_path), BASE)

        assert set(bodies[0]["options"]) == {"num_ctx"}


class TestAnthropicGatewayParameters:
    """Claude Code always sends max_tokens; the endpoint claims compatibility."""

    async def _messages(self, app, body):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/v1/messages", json=body, headers=META_HEADERS)

    ANTHROPIC_BASE = {
        "model": "daari",
        "messages": [{"role": "user", "content": "hello there"}],
        "max_tokens": 64,
    }

    @pytest.mark.asyncio
    async def test_anthropic_max_tokens_reaches_the_wire(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport(content=MOCK_MODEL_CONTENT)
        _patch_transport(monkeypatch, transport)
        response = await self._messages(_app(settings, tmp_path), self.ANTHROPIC_BASE)

        assert response.status_code == 200
        assert bodies[0]["options"]["num_predict"] == 64

    @pytest.mark.asyncio
    async def test_top_k_and_stop_sequences_reach_the_wire(
        self, settings, tmp_path, monkeypatch
    ):
        transport, bodies = _recording_transport(content=MOCK_MODEL_CONTENT)
        _patch_transport(monkeypatch, transport)
        await self._messages(
            _app(settings, tmp_path),
            {**self.ANTHROPIC_BASE, "top_k": 5, "stop_sequences": ["\n\nHuman:"]},
        )

        options = bodies[0]["options"]
        assert options["top_k"] == 5
        assert options["stop"] == ["\n\nHuman:"]


class TestOtherGatewaysCarryParameters:
    """Every surface that accepts a cap has to honor it, not just chat-completions."""

    async def _post_to(self, app, path, body):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path, json=body, headers=META_HEADERS)

    @pytest.mark.asyncio
    async def test_responses_max_output_tokens_reaches_the_wire(
        self, settings, tmp_path, monkeypatch
    ):
        transport, bodies = _recording_transport(content=MOCK_MODEL_CONTENT)
        _patch_transport(monkeypatch, transport)
        response = await self._post_to(
            _app(settings, tmp_path),
            "/v1/responses",
            {"model": "daari", "input": "hello there", "max_output_tokens": 12},
        )

        assert response.status_code == 200, response.text
        assert bodies[0]["options"]["num_predict"] == 12

    @pytest.mark.asyncio
    async def test_ollama_facade_passes_num_predict_through(
        self, settings, tmp_path, monkeypatch
    ):
        """JetBrains sends native Ollama options; only temperature survived before."""
        transport, bodies = _recording_transport(content=MOCK_MODEL_CONTENT)
        _patch_transport(monkeypatch, transport)
        response = await self._post_to(
            _app(settings, tmp_path),
            "/api/chat",
            {
                "model": "daari",
                "messages": [{"role": "user", "content": "hello there"}],
                "stream": False,
                "options": {"num_predict": 20, "top_k": 3, "seed": 5},
            },
        )

        assert response.status_code == 200, response.text
        options = bodies[0]["options"]
        assert options["num_predict"] == 20
        assert options["top_k"] == 3
        assert options["seed"] == 5


class TestWarningsSurfaceToTheClient:
    @pytest.mark.asyncio
    async def test_presence_penalty_produces_a_warning(self, settings, tmp_path, monkeypatch):
        transport, _ = _recording_transport()
        _patch_transport(monkeypatch, transport)
        response = await _post(_app(settings, tmp_path), {**BASE, "presence_penalty": 1.0})

        assert response.status_code == 200
        assert "presence_penalty" in response.json()["daari_meta"]["warning"]

    @pytest.mark.asyncio
    async def test_multiple_choices_produce_a_warning(self, settings, tmp_path, monkeypatch):
        transport, _ = _recording_transport()
        _patch_transport(monkeypatch, transport)
        response = await _post(_app(settings, tmp_path), {**BASE, "n": 3})

        assert "single choice" in response.json()["daari_meta"]["warning"]

    @pytest.mark.asyncio
    async def test_honored_parameters_add_no_warning(self, settings, tmp_path, monkeypatch):
        """A long answer avoids the router's own confidence warning."""
        transport, _ = _recording_transport(content=MOCK_MODEL_CONTENT)
        _patch_transport(monkeypatch, transport)
        response = await _post(_app(settings, tmp_path), {**BASE, "max_tokens": 20, "seed": 1})

        assert response.json()["daari_meta"].get("warning") is None

    @pytest.mark.asyncio
    async def test_a_sampling_warning_does_not_hide_an_existing_one(
        self, settings, tmp_path, monkeypatch
    ):
        """Low confidence is exactly when a client needs the full picture."""
        transport, _ = _recording_transport(content="short")
        _patch_transport(monkeypatch, transport)
        response = await _post(_app(settings, tmp_path), {**BASE, "n": 4})

        warning = response.json()["daari_meta"]["warning"]
        assert "below_confidence_threshold" in warning
        assert "single choice" in warning


class TestToolChoice:
    @pytest.mark.asyncio
    async def test_tool_choice_none_strips_tools(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        await _post(
            _app(settings, tmp_path),
            {**BASE, "tools": tools, "tool_choice": "none"},
        )

        assert "tools" not in bodies[0], "the client asked for no tools this turn"

    @pytest.mark.asyncio
    async def test_tool_choice_auto_keeps_tools(self, settings, tmp_path, monkeypatch):
        transport, bodies = _recording_transport()
        _patch_transport(monkeypatch, transport)
        tools = [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        await _post(
            _app(settings, tmp_path),
            {
                **BASE,
                "tools": tools,
                "tool_choice": "auto",
                "messages": [
                    {"role": "user", "content": "search it"},
                    {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
                ],
            },
        )

        assert bodies[0].get("tools"), "an active agent loop keeps its tools"


class TestCacheKeying:
    def _request(self, **sampling) -> InternalRequest:
        return InternalRequest(
            model="daari",
            messages=[Message(role="user", content="same question")],
            sampling=SamplingParams(**sampling),
        )

    def test_different_max_tokens_get_different_cache_keys(self):
        """Otherwise a 16-token answer is served to a request asking for 500."""
        assert cache_key(self._request(max_tokens=16)) != cache_key(
            self._request(max_tokens=500)
        )

    def test_different_seeds_get_different_cache_keys(self):
        assert cache_key(self._request(seed=1)) != cache_key(self._request(seed=2))

    def test_json_mode_does_not_collide_with_prose(self):
        assert cache_key(self._request(response_format_json=True)) != cache_key(
            self._request()
        )

    def test_identical_requests_still_share_a_key(self):
        assert cache_key(self._request(max_tokens=16)) == cache_key(
            self._request(max_tokens=16)
        )

    def test_a_dropped_parameter_does_not_fragment_the_cache(self):
        """`n` never reached the model, so it cannot have changed the answer."""
        assert cache_key(self._request(n=5)) == cache_key(self._request())

    def test_plain_requests_keep_their_pre_161_key(self):
        """Adding the fingerprint must not invalidate every existing entry."""
        plain = InternalRequest(
            model="daari", messages=[Message(role="user", content="same question")]
        )
        assert cache_key(plain) == cache_key(self._request())
