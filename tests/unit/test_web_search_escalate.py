"""web_search_options must escalate to L6 or fail closed — never silent local (#1295)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams, WebSearchUnavailable
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT, NoopEmbedder


def _semantic_cache(tmp_path) -> SemanticCache:
    return SemanticCache(
        path=str(tmp_path / "l1"),
        embedder=NoopEmbedder(),
        enabled=False,
    )


def _request(*, web_search: bool = True) -> InternalRequest:
    sampling = SamplingParams(
        web_search_options={"search_context_size": "medium"} if web_search else None
    )
    return InternalRequest(
        messages=[Message(role="user", content="what is the latest news on daari?")],
        model="llama3.2:3b",
        sampling=sampling,
    )


def _l3_response() -> InternalResponse:
    return InternalResponse(
        content=MOCK_MODEL_CONTENT,
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama",
            latency_ms=5,
        ),
    )


class TestRouterWebSearchEscalate:
    @pytest.mark.asyncio
    async def test_web_search_skips_local_and_goes_to_l6(self, tmp_path):
        local_called = False
        captured: dict = {}

        async def fake_l3(request: InternalRequest) -> InternalResponse:
            nonlocal local_called
            local_called = True
            return _l3_response()

        async def fake_l6(
            request: InternalRequest,
            *,
            escalated_from: str,
            local_confidence: float,
        ) -> InternalResponse:
            captured["request"] = request.model_copy(deep=True)
            captured["escalated_from"] = escalated_from
            return InternalResponse(
                content="Frontier search answer.",
                model="gpt-4o-mini",
                daari_meta=DaariMeta(
                    tier="L6",
                    executor="frontier",
                    provider_id="openai",
                    latency_ms=20,
                    escalated_from=escalated_from,
                    confidence=local_confidence,
                ),
            )

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]
        frontier = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="sk-test",
        )
        frontier.execute = fake_l6  # type: ignore[method-assign]

        router = Router(
            cache=ExactCache(str(tmp_path / "c"), enabled=False),
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=Metrics(),
            frontier=frontier,
            frontier_enabled=True,
        )

        result = await router.route(_request(web_search=True))
        assert local_called is False
        assert result.daari_meta.tier == "L6"
        assert result.daari_meta.warning == "web_search_required"
        assert captured["request"].sampling.web_search_options == {
            "search_context_size": "medium"
        }
        payload = captured["request"].sampling.openai_payload()
        assert payload["web_search_options"] == {"search_context_size": "medium"}

    @pytest.mark.asyncio
    async def test_no_frontier_raises_web_search_unavailable(self, tmp_path):
        async def fake_l3(request: InternalRequest) -> InternalResponse:
            raise AssertionError("local must not run when web search is required")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]

        router = Router(
            cache=ExactCache(str(tmp_path / "c"), enabled=False),
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=Metrics(),
            frontier_enabled=False,
        )

        with pytest.raises(WebSearchUnavailable) as excinfo:
            await router.route(_request(web_search=True))
        assert excinfo.value.reason in {"frontier_disabled", "web_search_required"}

    @pytest.mark.asyncio
    async def test_absent_web_search_keeps_local_path(self, tmp_path):
        async def fake_l3(request: InternalRequest) -> InternalResponse:
            return _l3_response()

        async def fake_l6(*args, **kwargs):
            raise AssertionError("L6 must not run for ordinary local-capable chat")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]
        frontier = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="sk-test",
        )
        frontier.execute = fake_l6  # type: ignore[method-assign]

        router = Router(
            cache=ExactCache(str(tmp_path / "c"), enabled=False),
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=Metrics(),
            frontier=frontier,
            frontier_enabled=True,
            confidence_threshold=0.0,
        )

        result = await router.route(_request(web_search=False))
        assert result.daari_meta.tier == "L3"
        assert result.daari_meta.warning != "web_search_required"


class TestGatewayWebSearchEscalate:
    @pytest.mark.asyncio
    async def test_asgi_web_search_reaches_l6_payload(self, settings, monkeypatch):
        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.frontier.enabled = True
        settings.frontier.base_url = "http://frontier.test/v1"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)
        captured: dict = {}

        async def fake_l3(request):
            raise AssertionError("local must not answer web_search_options")

        async def fake_l6(request, *, escalated_from: str, local_confidence: float):
            captured["payload"] = request.sampling.openai_payload()
            return InternalResponse(
                content="Search results from frontier.",
                model="gpt-4o-mini",
                daari_meta=DaariMeta(
                    tier="L6",
                    executor="frontier",
                    provider_id="openai",
                    latency_ms=10,
                    escalated_from=escalated_from,
                    confidence=local_confidence,
                    warning="web_search_required",
                ),
            )

        monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fake_l3)
        monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", fake_l3)
        monkeypatch.setattr(app.state.ctx.router.ollama_l5, "execute", fake_l3)
        monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_l6)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": "latest headlines?"}],
                    "web_search_options": {"search_context_size": "low"},
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["daari_meta"]["tier"] == "L6"
        assert body["daari_meta"]["warning"] == "web_search_required"
        assert captured["payload"]["web_search_options"] == {"search_context_size": "low"}

    @pytest.mark.asyncio
    async def test_asgi_no_frontier_header_returns_4xx(self, settings, monkeypatch):
        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.frontier.enabled = True
        settings.frontier.base_url = "http://frontier.test/v1"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        async def fake_l3(request):
            raise AssertionError("must not serve local when search is required")

        monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fake_l3)
        monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", fake_l3)
        monkeypatch.setattr(app.state.ctx.router.ollama_l5, "execute", fake_l3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": "latest headlines?"}],
                    "web_search_options": {"search_context_size": "medium"},
                },
                headers={**META_HEADERS, "X-Daari-No-Frontier": "true"},
            )
        assert response.status_code in {400, 403, 422, 501}, response.text
        detail = response.text.lower()
        assert "web_search" in detail or "frontier" in detail

    @pytest.mark.asyncio
    async def test_asgi_absent_web_search_stays_local(self, settings, monkeypatch):
        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.frontier.enabled = True
        settings.frontier.base_url = "http://frontier.test/v1"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        settings.routing.max_tier_for_chat = "L3"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        class Patched(real):
            def __init__(self, *args, **kwargs):
                if kwargs.get("transport") is None:
                    kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", Patched)

        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": "say hi"}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert response.json()["daari_meta"]["tier"] == "L3"


class TestDocsWebSearchEscalate:
    def test_clients_guide_mentions_web_search_escalate(self):
        from pathlib import Path

        text = Path("docs/developer/concepts/clients-and-gateways.md").read_text()
        assert "web_search_options" in text
        assert "L6" in text or "frontier" in text.lower()
