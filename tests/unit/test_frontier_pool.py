"""Multi-provider L6: fallback chains, key rotation, circuit breakers (#109)."""

from __future__ import annotations

import pytest

from daari.config.settings import FrontierProviderConfig, FrontierSettings, Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.trace import current_trace, end_trace, start_trace
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot, build_frontier_pool


def _request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="escalate me")],
        model="daari",
    )


def _ok(provider: str, model: str = "gpt-4o-mini") -> InternalResponse:
    return InternalResponse(
        content=f"answer from {provider}",
        model=model,
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id=provider,
            latency_ms=10,
            model=model,
        ),
    )


class TestCircuitBreaker:
    def test_opens_after_threshold(self):
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
        assert breaker.allow()
        breaker.record_failure()
        assert breaker.state == "closed"
        breaker.record_failure()
        assert breaker.state == "open"
        assert not breaker.allow()

    def test_half_open_after_cooldown(self):
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)
        breaker.record_failure()
        assert breaker.state == "half_open"
        assert breaker.allow()
        breaker.record_success()
        assert breaker.state == "closed"


class TestFrontierPool:
    @pytest.mark.asyncio
    async def test_falls_over_to_second_provider(self):
        primary = FrontierExecutor(
            base_url="http://primary", default_model="a", api_key="k1", provider="primary"
        )
        secondary = FrontierExecutor(
            base_url="http://secondary", default_model="b", api_key="k2", provider="secondary"
        )

        async def fail(**kwargs):
            raise RuntimeError("primary down")

        async def ok(request, *, escalated_from, local_confidence):
            return _ok("secondary", "b")

        primary.execute = fail  # type: ignore[method-assign]
        secondary.execute = ok  # type: ignore[method-assign]

        pool = FrontierPool(
            slots=[
                ProviderSlot(id="primary", executor=primary, keys=["k1"]),
                ProviderSlot(id="secondary", executor=secondary, keys=["k2"]),
            ]
        )
        start_trace()
        try:
            result = await pool.execute(
                _request(), escalated_from="L3", local_confidence=0.2
            )
            steps = [s["step"] for s in (current_trace().steps if current_trace() else [])]
        finally:
            end_trace()
        assert result.content == "answer from secondary"
        assert result.daari_meta.provider_id == "secondary"
        assert "frontier_fail" in steps and "frontier_ok" in steps

    @pytest.mark.asyncio
    async def test_skips_open_circuit(self):
        primary = FrontierExecutor(
            base_url="http://primary", default_model="a", api_key="k1", provider="primary"
        )
        secondary = FrontierExecutor(
            base_url="http://secondary", default_model="b", api_key="k2", provider="secondary"
        )
        called_primary = False

        async def primary_exec(**kwargs):
            nonlocal called_primary
            called_primary = True
            raise AssertionError("should not be called — circuit open")

        async def secondary_exec(request, *, escalated_from, local_confidence):
            return _ok("secondary")

        primary.execute = primary_exec  # type: ignore[method-assign]
        secondary.execute = secondary_exec  # type: ignore[method-assign]
        open_breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        open_breaker.record_failure()
        pool = FrontierPool(
            slots=[
                ProviderSlot(
                    id="primary", executor=primary, keys=["k1"], breaker=open_breaker
                ),
                ProviderSlot(id="secondary", executor=secondary, keys=["k2"]),
            ]
        )
        result = await pool.execute(_request(), escalated_from="L3", local_confidence=0.1)
        assert called_primary is False
        assert result.daari_meta.provider_id == "secondary"

    @pytest.mark.asyncio
    async def test_rotates_keys_across_calls(self):
        keys_seen: list[str] = []
        executor = FrontierExecutor(
            base_url="http://p", default_model="m", api_key="k1", provider="openai"
        )

        async def capture(request, *, escalated_from, local_confidence):
            keys_seen.append(executor.api_key or "")
            return _ok("openai")

        executor.execute = capture  # type: ignore[method-assign]
        pool = FrontierPool(
            slots=[ProviderSlot(id="openai", executor=executor, keys=["k1", "k2", "k3"])]
        )
        for _ in range(6):
            await pool.execute(_request(), escalated_from="L3", local_confidence=0.1)
        assert set(keys_seen) == {"k1", "k2", "k3"}
        assert len(keys_seen) == 6

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        executor = FrontierExecutor(
            base_url="http://p", default_model="m", api_key="k", provider="openai"
        )

        async def fail(**kwargs):
            raise RuntimeError("down")

        executor.execute = fail  # type: ignore[method-assign]
        pool = FrontierPool.from_single(executor)
        with pytest.raises(RuntimeError, match="all frontier providers failed"):
            await pool.execute(_request(), escalated_from="L3", local_confidence=0.1)


class TestBuildFromSettings:
    def test_scalar_shorthand(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-scalar")
        settings = Settings()
        settings.frontier = FrontierSettings(
            enabled=True, provider="openai", model="gpt-4o-mini"
        )
        pool = build_frontier_pool(settings)
        assert len(pool.slots) == 1
        assert pool.slots[0].executor.api_key == "sk-scalar"
        assert pool.slots[0].id == "openai"

    def test_providers_list(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_KEY", "or-key")
        settings = Settings()
        settings.frontier = FrontierSettings(
            enabled=True,
            providers=[
                FrontierProviderConfig(
                    id="openai",
                    base_url="https://api.openai.com/v1",
                    model="gpt-4o-mini",
                    keys=["sk-a", "sk-b"],
                ),
                FrontierProviderConfig(
                    id="openrouter",
                    base_url="https://openrouter.ai/api/v1",
                    model="openrouter/auto",
                    api_key_env="OPENROUTER_KEY",
                    failure_threshold=2,
                    cooldown_seconds=10,
                ),
            ],
        )
        pool = build_frontier_pool(settings)
        assert [s.id for s in pool.slots] == ["openai", "openrouter"]
        assert pool.slots[0].keys == ["sk-a", "sk-b"]
        assert "or-key" in pool.slots[1].keys
        assert pool.slots[1].breaker.failure_threshold == 2
