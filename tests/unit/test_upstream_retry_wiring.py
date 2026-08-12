"""Retries wired into the executors and the frontier pool (issue #159)."""

from __future__ import annotations

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.frontier import FrontierExecutor
from daari.router.retry import RetryPolicy
from daari.router.router import OllamaExecutor

FAST = RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0)


def _request(text: str = "hi") -> InternalRequest:
    return InternalRequest(model="daari", messages=[Message(role="user", content=text)])


def _chat_completion(content: str = "answer") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }


def _sequence_transport(responses: list) -> tuple[httpx.MockTransport, list[int]]:
    """A transport that walks `responses`, recording how many calls it saw."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        item = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), calls


class TestFrontierExecutor:
    @pytest.mark.asyncio
    async def test_transient_failure_then_success(self):
        transport, calls = _sequence_transport(
            [(503, {"error": "busy"}), (503, {"error": "busy"}), (200, _chat_completion())]
        )
        metrics = Metrics()
        executor = FrontierExecutor(
            base_url="http://upstream",
            default_model="gpt-4o",
            api_key="sk-test",
            transport=transport,
            retry=FAST,
            metrics=metrics,
        )

        response = await executor.execute(
            _request(), escalated_from="L5", local_confidence=0.2
        )

        assert response.content == "answer"
        assert len(calls) == 3
        assert metrics.upstream_retries == 2

    @pytest.mark.asyncio
    async def test_permanent_failure_still_fails(self):
        transport, calls = _sequence_transport([(500, {"error": "broken"})])
        executor = FrontierExecutor(
            base_url="http://upstream",
            default_model="gpt-4o",
            api_key="sk-test",
            transport=transport,
            retry=FAST,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await executor.execute(_request(), escalated_from="L5", local_confidence=0.2)
        assert len(calls) == 3, "retried to the budget, then surfaced the failure"

    @pytest.mark.asyncio
    async def test_bad_key_is_not_retried(self):
        transport, calls = _sequence_transport([(401, {"error": "bad key"})])
        executor = FrontierExecutor(
            base_url="http://upstream",
            default_model="gpt-4o",
            api_key="sk-wrong",
            transport=transport,
            retry=FAST,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await executor.execute(_request(), escalated_from="L5", local_confidence=0.2)
        assert len(calls) == 1, "retrying a rejected key only delays the error"

    @pytest.mark.asyncio
    async def test_connection_error_is_retried(self):
        transport, calls = _sequence_transport(
            [httpx.ConnectError("refused"), (200, _chat_completion("recovered"))]
        )
        executor = FrontierExecutor(
            base_url="http://upstream",
            default_model="gpt-4o",
            api_key="sk-test",
            transport=transport,
            retry=FAST,
        )

        response = await executor.execute(
            _request(), escalated_from="L5", local_confidence=0.2
        )
        assert response.content == "recovered"
        assert len(calls) == 2


def _patch_ollama_transport(monkeypatch, transport: httpx.MockTransport) -> None:
    """OllamaExecutor builds its own client, so inject at the httpx level."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


class TestOllamaExecutor:
    @pytest.mark.asyncio
    async def test_transient_failure_then_success(self, monkeypatch):
        transport, calls = _sequence_transport(
            [(503, {"error": "loading model"}), (200, {"message": {"content": "hello"}})]
        )
        _patch_ollama_transport(monkeypatch, transport)
        metrics = Metrics()
        executor = OllamaExecutor(
            base_url="http://ollama",
            default_model="llama3.2:3b",
            retry=FAST,
            metrics=metrics,
        )

        response = await executor.execute(_request())

        assert response.content == "hello"
        assert len(calls) == 2
        assert metrics.upstream_retries == 1

    @pytest.mark.asyncio
    async def test_malformed_request_is_not_retried(self, monkeypatch):
        transport, calls = _sequence_transport([(400, {"error": "bad payload"})])
        _patch_ollama_transport(monkeypatch, transport)
        executor = OllamaExecutor(
            base_url="http://ollama", default_model="llama3.2:3b", retry=FAST
        )

        with pytest.raises(Exception):
            await executor.execute(_request())
        assert len(calls) == 1


class _FlakyExecutor:
    """Stands in for a provider slot's executor, counting attempts."""

    def __init__(self, *, status: int, succeed_after: int | None = None) -> None:
        self.status = status
        self.succeed_after = succeed_after
        self.attempts = 0
        self.api_key: str | None = "sk-test"
        self.default_model = "model-x"
        self.metrics = None

    async def execute(self, request, *, escalated_from, local_confidence):
        self.attempts += 1
        if self.succeed_after is not None and self.attempts > self.succeed_after:
            from daari.gateway.internal import DaariMeta, InternalResponse

            return InternalResponse(
                content="ok",
                model=self.default_model,
                daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
            )
        req = httpx.Request("POST", "http://upstream/chat/completions")
        raise httpx.HTTPStatusError(
            "boom", request=req, response=httpx.Response(self.status, request=req)
        )


def _pool(*executors):
    from daari.router.circuit_breaker import CircuitBreaker
    from daari.router.frontier_pool import FrontierPool, ProviderSlot

    slots = [
        ProviderSlot(
            id=f"p{index}",
            executor=executor,
            keys=["sk-test"],
            weight=1.0,
            breaker=CircuitBreaker(failure_threshold=5, cooldown_seconds=60.0),
        )
        for index, executor in enumerate(executors)
    ]
    return FrontierPool(slots=slots, base_url="http://upstream", default_model="model-x")


class TestFrontierPoolFailover:
    @pytest.mark.asyncio
    async def test_failover_happens_after_the_executor_exhausts_its_retries(self):
        """The pool sees one exception per provider; retries live in the executor.

        This is what keeps a transient 429 from burning a provider slot.
        """
        unhealthy = _FlakyExecutor(status=503)
        healthy = _FlakyExecutor(status=503, succeed_after=0)
        pool = _pool(unhealthy, healthy)

        response = await pool.execute(_request(), escalated_from="L5", local_confidence=0.2)

        assert response.content == "ok"
        assert response.daari_meta.provider_id == "p1"
        assert unhealthy.attempts == 1, "the executor owns retries, not the pool"

    @pytest.mark.asyncio
    async def test_auth_failure_fails_over_immediately(self):
        rejected = _FlakyExecutor(status=401)
        healthy = _FlakyExecutor(status=503, succeed_after=0)
        pool = _pool(rejected, healthy)

        response = await pool.execute(_request(), escalated_from="L5", local_confidence=0.2)

        assert response.daari_meta.provider_id == "p1"
        assert rejected.attempts == 1

    @pytest.mark.asyncio
    async def test_all_providers_failing_raises(self):
        pool = _pool(_FlakyExecutor(status=503), _FlakyExecutor(status=500))
        with pytest.raises(RuntimeError, match="all frontier providers failed"):
            await pool.execute(_request(), escalated_from="L5", local_confidence=0.2)


class TestObservability:
    def test_prometheus_exposes_the_retry_counter(self):
        metrics = Metrics()
        metrics.record_upstream_retry()
        metrics.record_upstream_retry()
        text = render_prometheus(metrics)
        assert "# TYPE daari_upstream_retries_total counter" in text
        assert "daari_upstream_retries_total 2" in text

    @pytest.mark.asyncio
    async def test_retries_appear_as_trace_steps(self):
        """A slow request must show why it was slow."""
        from daari.observability.trace import end_trace, start_trace

        transport, _ = _sequence_transport(
            [(503, {"error": "busy"}), (200, _chat_completion())]
        )
        executor = FrontierExecutor(
            base_url="http://upstream",
            default_model="gpt-4o",
            api_key="sk-test",
            transport=transport,
            retry=FAST,
        )
        trace = start_trace()
        try:
            await executor.execute(_request(), escalated_from="L5", local_confidence=0.2)
        finally:
            end_trace()

        retries = [step for step in trace.steps if step.get("step") == "upstream_retry"]
        assert len(retries) == 1
        assert retries[0]["detail"]["status"] == 503
        assert retries[0]["detail"]["upstream"] == "frontier:openai"


class TestLedgerIsNotDoubleCounted:
    @pytest.mark.asyncio
    async def test_a_retried_request_records_one_ledger_row(self, tmp_path, monkeypatch):
        """Retries live below the ledger write, so one request stays one row.

        If retries were layered above accounting, a flaky upstream would inflate
        request counts and spend for traffic the client sent once.
        """
        from daari.config.settings import Settings
        from daari.observability.usage import UsageLedger
        from daari.router.router import AppContext

        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings()
        settings.usage.path = str(tmp_path / "usage.sqlite3")
        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        # Pin one tier: the local ladder would otherwise re-run on L4 and L5 and
        # confuse "retried the same tier" with "escalated to the next one".
        settings.routing.max_tier_for_chat = "L3"
        ctx = AppContext.from_settings(settings)
        ctx.router.usage_ledger = UsageLedger(tmp_path / "usage.sqlite3")

        transport, calls = _sequence_transport(
            [(503, {"error": "busy"}), (200, {"message": {"content": "hello"}})]
        )
        _patch_ollama_transport(monkeypatch, transport)
        for executor in (ctx.router.ollama_l3, ctx.router.ollama_l4, ctx.router.ollama_l5):
            executor.retry = FAST

        response = await ctx.router.route(_request("count me once"))

        assert response.content == "hello"
        assert len(calls) == 2, "the upstream was genuinely retried"

        report = ctx.router.usage_ledger.report(days=1)
        assert report["totals"]["requests"] == 1


class TestConfigDefaults:
    def test_local_and_frontier_timeouts_differ(self):
        from daari.config.settings import Settings

        upstream = Settings().upstream
        assert upstream.local_timeout_seconds == 120.0
        assert upstream.frontier_timeout_seconds == 90.0
        assert upstream.retry.attempts == 3

    def test_executors_receive_the_configured_policy(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings
        from daari.router.router import AppContext

        monkeypatch.setenv("HOME", str(tmp_path))
        settings = Settings()
        settings.upstream.retry.attempts = 5
        settings.upstream.local_timeout_seconds = 42.0
        ctx = AppContext.from_settings(settings)

        assert ctx.router.ollama_l3.retry is not None
        assert ctx.router.ollama_l3.retry.attempts == 5
        assert ctx.router.ollama_l3.timeout == 42.0
        assert ctx.router.ollama_l3.metrics is ctx.router.metrics
