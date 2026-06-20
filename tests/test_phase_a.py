from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache, cache_key
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import NoopEmbedder


@pytest.fixture
def settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
        }
    )


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


class TestL0Cache:
    def test_identical_requests_share_key(self):
        req_a = InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="llama3.2:3b",
        )
        req_b = InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="llama3.2:3b",
        )
        assert cache_key(req_a) == cache_key(req_b)

    def test_put_and_get(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)
        request = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="llama3.2:3b",
        )
        response = InternalResponse(
            content="hello",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )
        cache.put(request, response)
        hit = cache.get(request)
        assert hit is not None
        assert hit.content == "hello"


class TestRouter:
    @pytest.mark.asyncio
    async def test_l0_hit_on_repeat(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)
        metrics = Metrics()

        async def fake_execute(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="world",
                model="llama3.2:3b",
                daari_meta=DaariMeta(
                    tier="L3",
                    executor="ollama",
                    provider_id="ollama",
                    latency_ms=10,
                ),
            )

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_execute  # type: ignore[method-assign]

        router = Router(
            cache=cache,
            semantic_cache=SemanticCache(
                str(tmp_path / "l1"),
                NoopEmbedder(),
                enabled=False,
            ),
            ollama=ollama,
            metrics=metrics,
        )
        request = InternalRequest(
            messages=[Message(role="user", content="repeat me")],
            model="llama3.2:3b",
        )

        first = await router.route(request)
        assert first.daari_meta.tier == "L3"

        second = await router.route(request)
        assert second.daari_meta.tier == "L0"
        assert second.daari_meta.cache_hit is True
        assert metrics.tiers["L0"].count == 1


class TestOpenAIGateway:
    @pytest.mark.asyncio
    async def test_chat_completions_mocked(self, app, monkeypatch):
        async def fake_execute(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="pong",
                model="llama3.2:3b",
                daari_meta=DaariMeta(
                    tier="L3",
                    executor="ollama",
                    provider_id="ollama",
                    latency_ms=5,
                ),
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            ctx = app.state.ctx
            monkeypatch.setattr(ctx.router.ollama, "execute", fake_execute)

            payload = {
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "ping"}],
            }
            first = await client.post("/v1/chat/completions", json=payload)
            assert first.status_code == 200
            body = first.json()
            assert body["choices"][0]["message"]["content"] == "pong"
            assert body["daari_meta"]["tier"] == "L3"

            second = await client.post("/v1/chat/completions", json=payload)
            assert second.status_code == 200
            assert second.json()["daari_meta"]["tier"] == "L0"

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, app, monkeypatch):
        async def fake_execute(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="ok",
                model="llama3.2:3b",
                daari_meta=DaariMeta(
                    tier="L3",
                    executor="ollama",
                    provider_id="ollama",
                    latency_ms=1,
                ),
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
            await client.post(
                "/v1/chat/completions",
                json={"model": "llama3.2:3b", "messages": [{"role": "user", "content": "x"}]},
            )
            stats = await client.get("/v1/daari/stats")
            assert stats.status_code == 200
            assert stats.json()["total_requests"] == 1
