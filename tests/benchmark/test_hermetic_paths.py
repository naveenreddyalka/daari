"""Hermetic micro-benchmarks for cache / budget / rate-limit / batch paths (#477).

No Ollama. Marked ``@pytest.mark.benchmark`` so default CI skips them.
Ceilings are deliberately loose (~10× headroom over typical local means) so
only order-of-magnitude regressions fail.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import pytest

from daari.auth.budgets import budget_status
from daari.auth.rate_limit import RateLimiter, SqliteCounterBackend
from daari.auth.virtual_keys import BudgetWindow, VirtualKey
from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.batches import BatchStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

# Loose absolute ceilings (seconds). Documented so a 10× regression trips CI
# when someone opts into ``pytest -m benchmark``.
EXACT_CACHE_GET_CEILING_S = 0.050  # per get after warm put
BUDGET_STATUS_CEILING_S = 0.020  # per budget_status call
RATE_LIMIT_CHECK_CEILING_S = 0.100  # per SQLite-backed RateLimiter.check
BATCH_ENQUEUE_CEILING_S = 0.200  # per BatchStore.create (inline 1 request)
# N concurrent identical cold misses sharing one fill (#520).
L0_SINGLEFLIGHT_BURST_CEILING_S = 0.500
L0_SINGLEFLIGHT_CONCURRENCY = 32


class FakeLedger:
    enabled = True

    def __init__(self, spend: dict[str, float]) -> None:
        self.spend = spend

    def frontier_spend_usd_for_client(self, client_id, *, window="day", **_):
        return self.spend.get(f"{client_id}:{window}", 0.0)

    def frontier_spend_usd_for_client_days(self, client_id, *, days, **_):
        return self.spend.get(f"{client_id}:{days}d", 0.0)

    def requests_for_client(self, client_id, *, window="day", **_):
        return 0

    def requests_for_client_days(self, client_id, *, days, **_):
        return 0


def _request(content: str = "bench") -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=content)],
        model="llama3.2:3b",
    )


def _response() -> InternalResponse:
    return InternalResponse(
        content="cached",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L0", executor="cache", latency_ms=0),
    )


def _median(samples: list[float]) -> float:
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


@pytest.mark.benchmark
def test_exact_cache_get_under_ceiling(tmp_path):
    """L0 ExactCache.get after a warm put — diskcache path, no network."""
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    req = _request("exact-cache-bench")
    cache.put(req, _response())
    # Warm the handle / OS page cache once outside the timed loop.
    assert cache.get(req) is not None

    samples: list[float] = []
    for _ in range(40):
        start = time.perf_counter()
        hit = cache.get(req)
        samples.append(time.perf_counter() - start)
        assert hit is not None
        assert hit.content == "cached"

    median = _median(samples)
    assert median < EXACT_CACHE_GET_CEILING_S, (
        f"ExactCache.get median {median:.4f}s exceeds ceiling "
        f"{EXACT_CACHE_GET_CEILING_S}s (10×-regression guard)"
    )


@pytest.mark.benchmark
def test_budget_remaining_check_under_ceiling():
    """budget_status remaining computation — in-process ledger lookup."""
    key = VirtualKey(
        key_id="k1",
        name="bench",
        prefix="dk",
        client_id="key-bench",
        budget_windows=(BudgetWindow("day", 10.0), BudgetWindow("7d", 50.0)),
    )
    ledger = FakeLedger({"key-bench:day": 1.25, "key-bench:7d": 8.0})

    # Warm once.
    statuses = budget_status(
        key, None, ledger, client_id="key-bench", team_client_ids=[], now=NOW
    )
    assert statuses
    assert any(s.remaining > 0 for s in statuses)

    samples: list[float] = []
    for _ in range(80):
        start = time.perf_counter()
        statuses = budget_status(
            key, None, ledger, client_id="key-bench", team_client_ids=[], now=NOW
        )
        samples.append(time.perf_counter() - start)
        by_duration = {s.window.duration: s for s in statuses}
        assert by_duration["day"].remaining == pytest.approx(8.75)
        assert by_duration["7d"].remaining == pytest.approx(42.0)

    median = _median(samples)
    assert median < BUDGET_STATUS_CEILING_S, (
        f"budget_status median {median:.4f}s exceeds ceiling "
        f"{BUDGET_STATUS_CEILING_S}s (10×-regression guard)"
    )


@pytest.mark.benchmark
def test_sqlite_rate_limit_increment_under_ceiling(tmp_path):
    """RateLimiter.check with SqliteCounterBackend — durable RPM path."""
    backend = SqliteCounterBackend(tmp_path / "rate-limit.sqlite3")
    limiter = RateLimiter(backend, default_rpm=100_000)
    # Warm schema + first insert.
    decision = limiter.check(key_id="bench", model="llama3.2:3b", tokens=10)
    assert decision.allowed

    samples: list[float] = []
    for i in range(40):
        start = time.perf_counter()
        decision = limiter.check(
            key_id="bench", model="llama3.2:3b", tokens=10 + i
        )
        samples.append(time.perf_counter() - start)
        assert decision.allowed
        assert decision.backend == "sqlite"

    median = _median(samples)
    assert median < RATE_LIMIT_CHECK_CEILING_S, (
        f"SQLite RateLimiter.check median {median:.4f}s exceeds ceiling "
        f"{RATE_LIMIT_CHECK_CEILING_S}s (10×-regression guard)"
    )


@pytest.mark.benchmark
def test_batch_job_enqueue_under_ceiling(tmp_path):
    """BatchStore.create enqueue — durable sqlite job write path."""
    store = BatchStore(path=tmp_path / "batches.sqlite3")
    payload = [
        {
            "custom_id": "r1",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
        }
    ]
    # Warm path / schema.
    warm = store.create(endpoint="/v1/chat/completions", requests=payload)
    assert warm.id.startswith("batch_")

    samples: list[float] = []
    for i in range(20):
        start = time.perf_counter()
        job = store.create(
            endpoint="/v1/chat/completions",
            requests=[
                {
                    **payload[0],
                    "custom_id": f"r{i}",
                    "body": {
                        "model": "llama3.2:3b",
                        "messages": [{"role": "user", "content": f"hi-{i}"}],
                    },
                }
            ],
        )
        samples.append(time.perf_counter() - start)
        assert job.id.startswith("batch_")

    median = _median(samples)
    assert median < BATCH_ENQUEUE_CEILING_S, (
        f"BatchStore.create median {median:.4f}s exceeds ceiling "
        f"{BATCH_ENQUEUE_CEILING_S}s (10×-regression guard)"
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_l0_singleflight_concurrent_cold_miss_under_ceiling(tmp_path):
    """N identical cold misses → exactly one upstream within a wall ceiling (#520)."""
    cache = ExactCache(str(tmp_path / "c"), enabled=True)
    calls = 0
    release = asyncio.Event()
    entered = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        # Tiny synthetic work so wall time is measurable but tiny.
        await asyncio.sleep(0.001)
        return InternalResponse(
            content="A confident shared body with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=cache,
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"), NoopEmbedder(), enabled=False
        ),
        ollama=ollama,
        metrics=Metrics(),
        frontier_enabled=False,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="singleflight bench")],
        model="llama3.2:3b",
    )

    async def one() -> str:
        return (await router.route(request)).content

    start = time.perf_counter()
    tasks = [asyncio.create_task(one()) for _ in range(L0_SINGLEFLIGHT_CONCURRENCY)]
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    release.set()
    bodies = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    assert calls == 1, f"expected 1 upstream fill, got {calls}"
    assert len(set(bodies)) == 1
    assert elapsed < L0_SINGLEFLIGHT_BURST_CEILING_S, (
        f"L0 singleflight burst {elapsed:.4f}s exceeds ceiling "
        f"{L0_SINGLEFLIGHT_BURST_CEILING_S}s (stampede / coalesce regression)"
    )
