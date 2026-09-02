"""Local backend pool: health, load balancing, circuit breakers (issue #170)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import LocalBackendSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.prometheus import render_prometheus
from daari.observability.metrics import Metrics
from daari.observability.trace import end_trace, start_trace
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.local_pool import (
    BackendUnavailable,
    LocalBackendPool,
    LocalBackendSlot,
    build_local_pool,
)
from daari.router.router import AppContext, OllamaExecutor
from daari.server.app import create_app


CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _slot(
    backend_id: str,
    *,
    url: str = "http://127.0.0.1:11434",
    healthy: bool = True,
    outstanding: int = 0,
    model: str = "llama3.2:3b",
    tiers: list[str] | None = None,
    breaker: CircuitBreaker | None = None,
) -> LocalBackendSlot:
    return LocalBackendSlot(
        id=backend_id,
        base_url=url,
        kind="ollama",
        model=model,
        tiers=tiers or ["L3", "L4", "L5"],
        breaker=breaker or CircuitBreaker(),
        healthy=healthy,
        outstanding=outstanding,
    )


def _ok(backend_id: str = "local") -> InternalResponse:
    return InternalResponse(
        content="ok",
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama:l3",
            latency_ms=1,
            model="llama3.2:3b",
            backend_id=backend_id,
        ),
    )


class TestBuildLocalPool:
    def test_empty_config_synthesizes_ollama_host(self, settings):
        pool = build_local_pool(settings)
        assert len(pool.slots) == 1
        assert pool.slots[0].base_url == settings.ollama.base_url.rstrip("/")
        assert "L3" in pool.slots[0].tiers
        assert pool.strategy == "least_outstanding"

    def test_explicit_backends_are_per_tier(self, settings):
        settings.routing.local_pool.backends = [
            LocalBackendSettings(id="gpu-a", base_url="http://a:11434", tiers=["L3"]),
            LocalBackendSettings(id="gpu-b", base_url="http://b:11434", tiers=["L4", "L5"]),
        ]
        pool = build_local_pool(settings)
        assert [s.id for s in pool.slots_for("L3")] == ["gpu-a"]
        assert [s.id for s in pool.slots_for("L4")] == ["gpu-b"]


class TestPick:
    def test_least_outstanding_wins(self):
        pool = LocalBackendPool(
            strategy="least_outstanding",
            slots=[_slot("busy", outstanding=3), _slot("idle", outstanding=0)],
        )
        assert pool.pick("L3").id == "idle"

    def test_round_robin_cycles(self):
        pool = LocalBackendPool(
            strategy="round_robin",
            slots=[_slot("a"), _slot("b")],
        )
        assert pool.pick("L3").id == "a"
        assert pool.pick("L3").id == "b"
        assert pool.pick("L3").id == "a"

    def test_warm_model_preferred_among_hosts(self):
        pool = LocalBackendPool(
            strategy="least_outstanding",
            slots=[
                _slot("cold", model="llama3.2:3b", outstanding=0),
                _slot("warm", model="llama3.1:8b", outstanding=1),
            ],
        )
        picked = pool.pick("L3", warm_models={"llama3.1:8b"})
        assert picked.id == "warm"

    def test_skips_unhealthy_and_open_circuit(self):
        open_breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        open_breaker.record_failure()
        pool = LocalBackendPool(
            slots=[
                _slot("down", healthy=False),
                _slot("open", breaker=open_breaker),
                _slot("up"),
            ]
        )
        assert pool.pick("L3").id == "up"

    def test_all_down_raises(self):
        pool = LocalBackendPool(slots=[_slot("a", healthy=False), _slot("b", healthy=False)])
        with pytest.raises(BackendUnavailable) as exc:
            pool.pick("L3")
        assert exc.value.tier == "L3"


class TestExecute:
    @pytest.mark.asyncio
    async def test_failover_when_first_backend_errors(self):
        primary = OllamaExecutor(base_url="http://a", default_model="m", tier="L3")
        secondary = OllamaExecutor(base_url="http://b", default_model="m", tier="L3")

        async def fail(_request):
            raise RuntimeError("primary down")

        async def ok(_request):
            return _ok("gpu-b")

        primary.execute = fail  # type: ignore[method-assign]
        secondary.execute = ok  # type: ignore[method-assign]

        pool = LocalBackendPool(
            slots=[
                _slot("gpu-a", url="http://a"),
                _slot("gpu-b", url="http://b"),
            ]
        )
        start_trace()
        try:
            response = await pool.execute(
                "L3",
                InternalRequest(messages=[], model="m"),
                executors={"gpu-a": primary, "gpu-b": secondary},
            )
        finally:
            end_trace()
        assert response.content == "ok"
        assert response.daari_meta.backend_id == "gpu-b"
        assert pool.slots[0].breaker.failures >= 1

    @pytest.mark.asyncio
    async def test_all_fail_raises_backend_unavailable(self):
        async def fail(_request):
            raise RuntimeError("down")

        a = OllamaExecutor(base_url="http://a", default_model="m", tier="L3")
        b = OllamaExecutor(base_url="http://b", default_model="m", tier="L3")
        a.execute = fail  # type: ignore[method-assign]
        b.execute = fail  # type: ignore[method-assign]
        pool = LocalBackendPool(slots=[_slot("a", url="http://a"), _slot("b", url="http://b")])
        with pytest.raises(BackendUnavailable):
            await pool.execute(
                "L3",
                InternalRequest(messages=[], model="m"),
                executors={"a": a, "b": b},
            )


class TestReadiness:
    def test_ready_degraded_unavailable(self):
        pool = LocalBackendPool(
            slots=[_slot("a", healthy=True), _slot("b", healthy=False)]
        )
        snap = pool.readiness()
        assert snap["status"] == "degraded"
        assert snap["http_status"] == 200

        pool.slots[0].healthy = False
        snap = pool.readiness()
        assert snap["status"] == "not_ready"
        assert snap["http_status"] == 503

        pool.slots[0].healthy = True
        pool.slots[1].healthy = True
        snap = pool.readiness()
        assert snap["status"] == "ready"
        assert snap["http_status"] == 200


class TestHealthLoop:
    @pytest.mark.asyncio
    async def test_check_health_marks_down_without_blocking_pick(self, monkeypatch):
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_probe(_url: str, timeout: float = 2.0) -> str:
            started.set()
            await release.wait()
            return "ConnectError"

        monkeypatch.setattr("daari.router.local_pool.check_model_backend", slow_probe)
        pool = LocalBackendPool(slots=[_slot("solo")])
        task = asyncio.create_task(pool.check_health())
        await started.wait()
        assert pool.pick("L3").id == "solo"
        release.set()
        await task
        with pytest.raises(BackendUnavailable):
            pool.pick("L3")


def _app(settings, *, pool: LocalBackendPool | None = None):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    if pool is not None:
        application.state.ctx.local_pool = pool
        application.state.ctx.router.local_pool = pool

    async def fake(_request):
        return _ok("local")

    application.state.ctx.router.ollama_l3.execute = fake
    application.state.ctx.router.ollama_l4.execute = fake
    application.state.ctx.router.ollama_l5.execute = fake
    return application


@pytest.mark.asyncio
async def test_one_backend_down_still_serves(settings):
    settings.routing.local_pool.backends = [
        LocalBackendSettings(id="dead", base_url="http://127.0.0.1:1"),
        LocalBackendSettings(id="live", base_url="http://127.0.0.1:11434"),
    ]
    app = _app(settings)
    pool = app.state.ctx.router.local_pool
    assert pool is not None
    pool.slots[0].healthy = False

    async def fake(_request):
        return _ok("live")

    live = replace(app.state.ctx.router.ollama_l3, base_url="http://127.0.0.1:11434")
    live.execute = fake  # type: ignore[method-assign]
    pool.bind_executor = lambda slot, template: live  # type: ignore[method-assign]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_all_backends_down_is_typed_503(settings):
    settings.routing.local_pool.backends = [
        LocalBackendSettings(id="a", base_url="http://127.0.0.1:1"),
        LocalBackendSettings(id="b", base_url="http://127.0.0.1:2"),
    ]
    app = _app(settings)
    for slot in app.state.ctx.router.local_pool.slots:
        slot.healthy = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT)
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "backend_unavailable"


@pytest.mark.asyncio
async def test_ready_degraded_when_some_backends_down(settings, monkeypatch):
    settings.routing.local_pool.backends = [
        LocalBackendSettings(id="a", base_url="http://a:11434"),
        LocalBackendSettings(id="b", base_url="http://b:11434"),
    ]
    app = _app(settings)
    app.state.ctx.router.local_pool.slots[0].healthy = True
    app.state.ctx.router.local_pool.slots[0].last_check = "ok"
    app.state.ctx.router.local_pool.slots[1].healthy = False
    app.state.ctx.router.local_pool.slots[1].last_check = "ConnectError"
    app.state.ctx.local_pool = app.state.ctx.router.local_pool
    app.state.ctx.local_pool.checked = True

    async def unused(_url: str, timeout: float = 2.0) -> str:
        raise AssertionError("ready should use the pool snapshot")

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", unused)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert any(item["id"] == "b" and not item["healthy"] for item in body["backends"])


class TestOpenAIKind:
    @pytest.mark.asyncio
    async def test_health_probe_uses_v1_models(self, monkeypatch):
        seen: list[str] = []

        async def capture(url: str, timeout: float = 2.0) -> str:
            seen.append(url)
            return "ok"

        monkeypatch.setattr("daari.router.local_pool.check_model_backend", capture)
        pool = LocalBackendPool(
            slots=[
                LocalBackendSlot(
                    id="vllm-a",
                    base_url="http://127.0.0.1:8000",
                    kind="openai",
                    model="meta-llama/Llama-3.1-8B",
                    tiers=["L4"],
                )
            ]
        )
        await pool.check_health()
        assert seen == ["http://127.0.0.1:8000/v1/models"]

    @pytest.mark.asyncio
    async def test_serves_l4_and_sets_backend_id(self, monkeypatch):
        from daari.router.openai_executor import OpenAICompatExecutor

        seen: dict = {}

        def handler(request):
            import httpx

            seen["path"] = request.url.path
            seen["body"] = request.read()
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "from-vllm"},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

        transport = __import__("httpx").MockTransport(handler)
        original = __import__("httpx").AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr("daari.router.openai_executor.httpx.AsyncClient", patched_client)

        template = OllamaExecutor(base_url="http://ollama", default_model="llama3.1:8b", tier="L4")
        pool = LocalBackendPool(
            slots=[
                LocalBackendSlot(
                    id="vllm-a",
                    base_url="http://127.0.0.1:8000",
                    kind="openai",
                    model="meta-llama/Llama-3.1-8B",
                    tiers=["L4"],
                )
            ]
        )
        bound = pool.bind_executor(template=template, slot=pool.slots[0])
        assert isinstance(bound, OpenAICompatExecutor)
        response = await pool.execute(
            "L4",
            InternalRequest(messages=[], model="llama3.1:8b"),
            template=template,
        )
        assert response.content == "from-vllm"
        assert response.daari_meta.backend_id == "vllm-a"
        assert response.daari_meta.executor == "openai"
        assert seen["path"] == "/v1/chat/completions"
        assert b"meta-llama/Llama-3.1-8B" in seen["body"]

    @pytest.mark.asyncio
    async def test_failure_trips_circuit_breaker(self):
        template = OllamaExecutor(base_url="http://ollama", default_model="m", tier="L4")

        async def fail(_request):
            raise RuntimeError("vllm down")

        pool = LocalBackendPool(
            slots=[
                LocalBackendSlot(
                    id="vllm-a",
                    base_url="http://127.0.0.1:8000",
                    kind="openai",
                    model="meta-llama/Llama-3.1-8B",
                    tiers=["L4"],
                    breaker=CircuitBreaker(failure_threshold=1, cooldown_seconds=60),
                )
            ]
        )
        bound = pool.bind_executor(slot=pool.slots[0], template=template)
        bound.execute = fail  # type: ignore[method-assign]
        with pytest.raises(BackendUnavailable):
            await pool.execute(
                "L4",
                InternalRequest(messages=[], model="m"),
                executors={"vllm-a": bound},
            )
        assert pool.slots[0].breaker.failures >= 1
        assert pool.slots[0].breaker.state == "open"


def test_openai_kind_accepted_in_settings():
    entry = LocalBackendSettings(
        id="vllm-a",
        kind="openai",
        base_url="http://127.0.0.1:8000",
        model="meta-llama/Llama-3.1-8B",
        tiers=["L4"],
    )
    assert entry.kind == "openai"


def test_metrics_label_chosen_backend():
    metrics = Metrics()
    metrics.record("L3", latency_ms=5, backend_id="gpu-a")
    text = render_prometheus(
        metrics,
        backend_pool={
            "backends": [
                {"id": "gpu-a", "healthy": True, "outstanding": 1, "requests": 4},
                {"id": "gpu-b", "healthy": False, "outstanding": 0, "requests": 0},
            ]
        },
    )
    assert 'daari_backend_up{backend="gpu-a"} 1' in text or 'daari_backend_up{backend="gpu-a"}' in text
    assert "daari_backend_up" in text
    assert "gpu-a" in text
    assert "daari_backend_requests_total" in text
