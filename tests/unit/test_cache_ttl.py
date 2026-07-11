"""L0/L1 cache TTLs, prune, and category TTL overrides (issue #36)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import CategoryPolicy
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class ConstEmbedder:
    async def embed(self, text: str) -> list[float] | None:
        return [1.0, 0.0]


def _request(text: str = "what is a cache?") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


def _response(content: str = "cached answer") -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


class TestExactCacheTTL:
    def test_fresh_entry_hits_expired_entry_misses(self, tmp_path):
        clock = FakeClock()
        cache = ExactCache(str(tmp_path / "l0"), enabled=True, ttl_seconds=100, clock=clock)
        cache.put(_request(), _response())

        clock.now += 50
        assert cache.get(_request()) is not None

        clock.now += 100
        assert cache.get(_request()) is None
        # expired entry removed lazily
        clock.now -= 100
        assert cache.get(_request()) is None

    def test_zero_ttl_never_expires(self, tmp_path):
        clock = FakeClock()
        cache = ExactCache(str(tmp_path / "l0"), enabled=True, ttl_seconds=0, clock=clock)
        cache.put(_request(), _response())
        clock.now += 10_000_000
        assert cache.get(_request()) is not None

    def test_max_age_override_beats_default_ttl(self, tmp_path):
        clock = FakeClock()
        cache = ExactCache(str(tmp_path / "l0"), enabled=True, ttl_seconds=0, clock=clock)
        cache.put(_request(), _response())
        clock.now += 60
        assert cache.get(_request(), max_age=30) is None
        cache.put(_request(), _response())
        assert cache.get(_request(), max_age=30) is not None

    def test_prune_removes_only_expired(self, tmp_path):
        clock = FakeClock()
        cache = ExactCache(str(tmp_path / "l0"), enabled=True, ttl_seconds=100, clock=clock)
        cache.put(_request("old entry"), _response())
        clock.now += 150
        cache.put(_request("fresh entry"), _response())

        removed = cache.prune()
        assert removed == 1
        assert cache.get(_request("fresh entry")) is not None


class TestSemanticCacheTTL:
    @pytest.mark.asyncio
    async def test_expired_entry_not_matched(self, tmp_path):
        clock = FakeClock()
        cache = SemanticCache(
            str(tmp_path / "l1"),
            ConstEmbedder(),
            enabled=True,
            similarity_threshold=0.8,
            ttl_seconds=100,
            clock=clock,
        )
        await cache.put(_request(), _response())

        clock.now += 50
        hit, _ = await cache.get(_request())
        assert hit is not None

        clock.now += 100
        miss, _ = await cache.get(_request())
        assert miss is None

    @pytest.mark.asyncio
    async def test_prune_removes_expired_entries(self, tmp_path):
        clock = FakeClock()
        cache = SemanticCache(
            str(tmp_path / "l1"),
            ConstEmbedder(),
            enabled=True,
            ttl_seconds=100,
            clock=clock,
        )
        await cache.put(_request("old"), _response())
        clock.now += 150
        await cache.put(_request("fresh"), _response())

        removed = cache.prune()
        assert removed == 1
        hit, _ = await cache.get(_request("fresh"))
        assert hit is not None


class TestCachePruneCLI:
    def test_cache_prune_reports_counts(self, tmp_path, monkeypatch):
        import time as real_time

        from typer.testing import CliRunner

        from daari.cli.app import app
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {
                "cache": {
                    "l0": {"enabled": True, "path": str(tmp_path / "l0"), "ttl_seconds": 100},
                    "l1": {"enabled": True, "path": str(tmp_path / "l1"), "ttl_seconds": 100},
                }
            }
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

        # Write an already-expired L0 entry by faking the write-time clock.
        stale = ExactCache(
            str(tmp_path / "l0"), enabled=True, ttl_seconds=100, clock=lambda: real_time.time() - 500
        )
        stale.put(_request("stale"), _response())

        result = CliRunner().invoke(app, ["cache", "prune"])
        assert result.exit_code == 0
        assert "L0: removed 1 expired entries" in result.stdout
        assert "L1: removed 0 expired entries" in result.stdout


class TestCategoryTTLOverride:
    @pytest.mark.asyncio
    async def test_policy_ttl_expires_l0_entry(self, tmp_path):
        clock = FakeClock()
        cache = ExactCache(str(tmp_path / "l0"), enabled=True, ttl_seconds=0, clock=clock)
        executed: list[str] = []

        async def fake_execute(_request: InternalRequest) -> InternalResponse:
            executed.append("model")
            return _response("fresh from model")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_execute  # type: ignore[method-assign]
        router = Router(
            cache=cache,
            semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
            ollama=ollama,
            metrics=Metrics(),
            category_policies={"doc_qa": CategoryPolicy(ttl_seconds=10)},
        )
        # "what is a cache?" categorizes as doc_qa
        request = _request("what is a cache?")
        cache.put(request, _response("stale doc answer"))

        clock.now += 60
        response = await router.route(request)
        assert executed == ["model"]
        assert response.content == "fresh from model"
