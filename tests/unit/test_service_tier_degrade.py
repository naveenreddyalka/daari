"""OpenAI service_tier org/project restriction → one degrade retry (#1867)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor, is_openai_service_tier_restriction
from daari.router.retry import RetryPolicy


def _request(*, service_tier: str | None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o-mini",
        sampling=SamplingParams(max_tokens=16, service_tier=service_tier),
    )


def _tier_error() -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "error": {
                "message": (
                    "Invalid `service_tier` argument: The requested service "
                    "tier is not allowed for this project."
                ),
                "type": "invalid_request_error",
                "param": "service_tier",
                "code": "invalid_value",
            }
        },
    )


def _ok(*, service_tier: str = "default") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "service_tier": service_tier,
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    )


def _stream_sse(*, service_tier: str = "default") -> bytes:
    delta = {
        "id": "chatcmpl-s",
        "object": "chat.completion.chunk",
        "choices": [{"delta": {"content": "ok"}, "finish_reason": None}],
    }
    usage = {
        "id": "chatcmpl-s",
        "object": "chat.completion.chunk",
        "service_tier": service_tier,
        "choices": [],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    return (f"data: {json.dumps(delta)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n").encode()


def test_detects_service_tier_restriction_by_param():
    assert is_openai_service_tier_restriction(_tier_error()) is True


def test_non_tier_400_is_not_restriction():
    other = httpx.Response(
        400,
        json={
            "error": {
                "message": "Invalid `temperature`",
                "type": "invalid_request_error",
                "param": "temperature",
                "code": "invalid_value",
            }
        },
    )
    assert is_openai_service_tier_restriction(other) is False


@pytest.mark.asyncio
async def test_service_tier_400_retries_once_without_tier_and_bills_response():
    tiers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tiers.append(body.get("service_tier"))
        if body.get("service_tier") == "priority":
            return _tier_error()
        return _ok(service_tier="default")

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        metrics=metrics,
        retry=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(service_tier="priority"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert tiers == ["priority", None]
    assert response.daari_meta.service_tier == "default"
    assert "service_tier_degraded" in (response.daari_meta.warning or "")
    assert metrics.soft_warnings.get("service_tier_degraded") == 1


@pytest.mark.asyncio
async def test_non_tier_400_passthrough_no_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid `max_tokens`",
                    "type": "invalid_request_error",
                    "param": "max_tokens",
                    "code": "invalid_value",
                }
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        retry=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await executor.execute(
            _request(service_tier="flex"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    assert excinfo.value.response.status_code == 400
    assert calls == 1


@pytest.mark.asyncio
async def test_streamed_service_tier_400_retries_once_without_tier():
    from daari.gateway.cost_headers import WARNING_HEADER, StreamOutcome

    tiers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tiers.append(body.get("service_tier"))
        if body.get("service_tier") == "flex":
            return _tier_error()
        return httpx.Response(
            200,
            content=_stream_sse(service_tier="default"),
            headers={"content-type": "text/event-stream"},
        )

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        metrics=metrics,
        transport=httpx.MockTransport(handler),
    )
    events = [
        event
        async for event in executor.stream(
            _request(service_tier="flex"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    ]
    assert tiers == ["flex", None]
    assert events == ["ok"]
    assert executor.last_stream_service_tier == "default"
    meta = DaariMeta(tier="L6", executor="frontier")
    outcome = StreamOutcome(tier="L6", cache="miss")
    executor.apply_service_tier_degraded_warning(meta)
    executor.apply_service_tier_degraded_warning(outcome)
    assert meta.warning == "service_tier_degraded"
    assert outcome.headers()[WARNING_HEADER] == "service_tier_degraded"
    assert metrics.soft_warnings.get("service_tier_degraded") == 1


@pytest.mark.asyncio
async def test_degrade_spend_and_cost_use_served_tier(settings, tmp_path, monkeypatch):
    """After priority→default degrade, spend + cost use default (1×), not priority (#1885)."""
    from daari.gateway.cost_headers import COST_HEADER
    from daari.pricing import cost_usd, service_tier_factor
    from daari.router.router import AppContext
    from daari.server.app import create_app
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import META_HEADERS

    settings.frontier.enabled = True
    settings.frontier.confidence_threshold = 0.99
    settings.frontier.provider = "openai"
    settings.frontier.model = "gpt-4o-mini"
    settings.frontier.base_url = "https://api.openai.com/v1"
    settings.cache.l0.enabled = False
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("service_tier") == "priority":
            return _tier_error()
        return _ok(service_tier="default")

    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.ctx.router.frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
    )
    application.state.ctx.router.frontier_enabled = True

    async def short_local(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="no",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    for tier in ("ollama_l3", "ollama_l4", "ollama_l5"):
        monkeypatch.setattr(getattr(application.state.ctx.router, tier), "execute", short_local)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "escalate please"}],
                "service_tier": "priority",
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["daari_meta"]["service_tier"] == "default"
    assert "service_tier_degraded" in (body["daari_meta"].get("warning") or "")
    expected = cost_usd(
        "gpt-4o-mini",
        3,
        2,
        settings.pricing,
        fallback_per_1k=float(settings.frontier.price_per_1k_tokens or 0.002),
        service_tier="default",
    )
    priority_cost = cost_usd(
        "gpt-4o-mini",
        3,
        2,
        settings.pricing,
        fallback_per_1k=float(settings.frontier.price_per_1k_tokens or 0.002),
        service_tier="priority",
    )
    assert service_tier_factor("priority") == 2.0
    assert priority_cost == pytest.approx(expected * 2.0)
    assert float(response.headers[COST_HEADER]) == pytest.approx(expected)
    ledger = application.state.ctx.router.spend_ledger
    rows = list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert rows, "expected a spend row"
    row = rows[-1]
    cost = row["cost_usd"] if isinstance(row, dict) else row.cost_usd
    assert float(cost) == pytest.approx(expected)


def test_stream_bill_includes_served_service_tier(tmp_path):
    """Stream bill meta must carry last_stream_service_tier for cost/spend (#1885)."""
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.cost_headers import stream_usage_cost
    from daari.observability.metrics import Metrics
    from daari.pricing import cost_usd
    from daari.router.router import OllamaExecutor, Router
    from daari.config.settings import Settings
    from tests.conftest import NoopEmbedder

    settings = Settings()
    frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
    )
    frontier.last_stream_input_tokens = 3
    frontier.last_stream_output_tokens = 2
    frontier.last_stream_service_tier = "priority"
    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=ollama,
        ollama_l4=ollama,
        ollama_l5=ollama,
        frontier=frontier,
        metrics=Metrics(),
        pricing=settings.pricing,
        frontier_price_per_1k_tokens=0.002,
    )
    served, tokens = router._anthropic_stream_bill("ok", fallback_model="gpt-4o-mini")
    assert tokens == (3, 2)
    assert served is not None
    assert served.daari_meta.service_tier == "priority"
    streamed = stream_usage_cost(
        tier="L6",
        model="gpt-4o-mini",
        prompt_tokens=3,
        completion_tokens=2,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        service_tier=served.daari_meta.service_tier,
    )
    expected = cost_usd(
        "gpt-4o-mini",
        3,
        2,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="priority",
    )
    assert streamed == pytest.approx(expected)

    frontier.last_stream_service_tier = "default"
    degraded, _ = router._anthropic_stream_bill("ok", fallback_model="gpt-4o-mini")
    assert degraded is not None
    assert degraded.daari_meta.service_tier == "default"
    assert router._stream_usage_cost(
        "L6", prompt_tokens=3, completion_tokens=2, served=degraded
    ) == pytest.approx(
        cost_usd(
            "gpt-4o-mini",
            3,
            2,
            settings.pricing,
            fallback_per_1k=0.002,
            service_tier="default",
        )
    )
