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
from daari.auth.rate_limit import (
    MemoryCounterBackend,
    RATELIMIT_WARNING_HEADER,
    RateLimiter,
    SqliteCounterBackend,
)
from daari.auth.virtual_keys import BudgetWindow, VirtualKey
from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.batches import BatchStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
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
# N concurrent same-embed-key L1 cold misses (distinct L0 keys) (#528).
L1_SINGLEFLIGHT_BURST_CEILING_S = 0.750
L1_SINGLEFLIGHT_CONCURRENCY = 32
# N concurrent soft-band RPM requests (memory limiter + frozen window) (#540).
# ASGI+httpx burst on shared runners is ~1–2s; keep ~2× headroom.
SOFT_RATE_LIMIT_BURST_CEILING_S = 5.000
SOFT_RATE_LIMIT_CONCURRENCY = 32
SOFT_RATE_LIMIT_RPM = 200
SOFT_RATE_LIMIT_PREFILL = 159  # soft line at 0.8 * 200 = 160
# N concurrent TTFT preference rewrites (seeded histograms, ttft_aware) (#574).
TTFT_PREFERENCE_BURST_CEILING_S = 0.500
TTFT_PREFERENCE_CONCURRENCY = 32
# N concurrent hard 429s after RPM exhausted (memory limiter + frozen window) (#585).
HARD_REJECT_BURST_CEILING_S = 5.000
HARD_REJECT_CONCURRENCY = 32
HARD_REJECT_RPM = 10
# N concurrent hard 402s after USD budget / request quota exhausted (#592).
HARD_402_BURST_CEILING_S = 5.000
HARD_402_CONCURRENCY = 32
# N concurrent soft-band request-quota warns (VK + ledger prefill) (#620).
SOFT_REQUEST_QUOTA_BURST_CEILING_S = 5.000
SOFT_REQUEST_QUOTA_CONCURRENCY = 32
SOFT_REQUEST_QUOTA_CAP = 200
SOFT_REQUEST_QUOTA_PREFILL = 160  # soft line at 0.8 * 200 = 160


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


class _BarrierEmbedder:
    """Blocks inside embed until release so concurrent L1 nearest calls overlap."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [1.0, 0.0, 0.0]
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return list(self.vector)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_l1_singleflight_concurrent_cold_miss_under_ceiling(tmp_path):
    """N same-embed-key cold misses → 1 embed + 1 upstream under a wall ceiling (#528)."""
    from daari.cache.exact import cache_key
    from daari.cache.normalize import normalize_for_embedding
    from daari.cache.semantic import extract_embed_text, l1_flight_key

    embedder = _BarrierEmbedder()
    # Instant embeds after the timed barrier phase (L1 put after fill).
    embedder.release.set()

    cache = ExactCache(str(tmp_path / "c"), enabled=True)
    upstream_calls = 0
    release = asyncio.Event()
    entered = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal upstream_calls
        upstream_calls += 1
        entered.set()
        await release.wait()
        await asyncio.sleep(0.001)
        return InternalResponse(
            content="A confident l1-shared body with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    semantic = SemanticCache(
        str(tmp_path / "l1"),
        embedder,
        enabled=True,
        similarity_threshold=0.99,
    )
    router = Router(
        cache=cache,
        semantic_cache=semantic,
        ollama=ollama,
        metrics=Metrics(),
        frontier_enabled=False,
    )

    # Distinct L0 keys, identical normalized embed text → L1 singleflight key.
    requests = [
        InternalRequest(
            messages=[Message(role="user", content=f"hello{' ' * (i + 1)}world")],
            model="llama3.2:3b",
        )
        for i in range(L1_SINGLEFLIGHT_CONCURRENCY)
    ]
    assert len({cache_key(r) for r in requests}) == L1_SINGLEFLIGHT_CONCURRENCY
    flight_keys = {
        l1_flight_key(r, text=normalize_for_embedding(extract_embed_text(r)))
        for r in requests
    }
    assert len(flight_keys) == 1

    embedder.calls = 0
    embedder.entered.clear()
    embedder.release.clear()

    start = time.perf_counter()
    tasks = [asyncio.create_task(router.route(r)) for r in requests]
    await asyncio.wait_for(embedder.entered.wait(), timeout=2.0)
    # Unblock the shared embed so nearest can miss and the fill flight starts.
    embedder.release.set()
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    # Nearest phase must have coalesced before the shared upstream starts.
    assert embedder.calls == 1, f"expected 1 embed before fill, got {embedder.calls}"
    release.set()
    bodies = [(await t).content for t in tasks]
    elapsed = time.perf_counter() - start

    assert upstream_calls == 1, f"expected 1 upstream fill, got {upstream_calls}"
    assert len(set(bodies)) == 1
    assert elapsed < L1_SINGLEFLIGHT_BURST_CEILING_S, (
        f"L1 singleflight burst {elapsed:.4f}s exceeds ceiling "
        f"{L1_SINGLEFLIGHT_BURST_CEILING_S}s (embed/upstream stampede regression)"
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_soft_rate_limit_warn_burst_under_ceiling(settings, monkeypatch):
    """N concurrent soft-band requests → 200 + soft header under a wall ceiling (#540)."""
    from httpx import ASGITransport, AsyncClient

    # Freeze mid-window so RPM soft-band counts stay stable (same as #526 unit tests).
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    settings.frontier.soft_budget_ratio = 0.8

    limiter = RateLimiter(MemoryCounterBackend(), default_rpm=SOFT_RATE_LIMIT_RPM)
    # Open installs (no master/VK) rate-limit under key_id "master" (auth.py).
    for _ in range(SOFT_RATE_LIMIT_PREFILL):
        decision = limiter.check(key_id="master", model="daari", tokens=8)
        assert decision.allowed

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.rate_limiter = limiter

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A confident soft-band body with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    chat = {"model": "daari", "messages": [{"role": "user", "content": "soft-burst"}]}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def one():
            return await client.post(
                "/v1/chat/completions",
                json=chat,
                headers={"X-Daari-No-Cache": "true"},
            )

        start = time.perf_counter()
        responses = await asyncio.gather(
            *[one() for _ in range(SOFT_RATE_LIMIT_CONCURRENCY)]
        )
        elapsed = time.perf_counter() - start

    assert all(r.status_code == 200 for r in responses), [
        r.status_code for r in responses
    ]
    assert all(r.headers.get(RATELIMIT_WARNING_HEADER) == "soft" for r in responses)
    assert elapsed < SOFT_RATE_LIMIT_BURST_CEILING_S, (
        f"soft rate-limit burst {elapsed:.4f}s exceeds ceiling "
        f"{SOFT_RATE_LIMIT_BURST_CEILING_S}s (soft-header middleware regression)"
    )


@pytest.mark.benchmark
def test_ttft_preference_rewrite_burst_under_ceiling(tmp_path):
    """N concurrent TTFT preference rewrites → all L3; counter ≥ N under a wall (#574)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    for _ in range(30):
        metrics.record_ttft("L3", ttft_ms=30)
        metrics.record_ttft("L4", ttft_ms=400)

    cache = ExactCache(str(tmp_path / "l0"), enabled=False)
    semantic = SemanticCache(
        str(tmp_path / "l1"), NoopEmbedder(), enabled=False
    )
    router = Router(
        cache=cache,
        semantic_cache=semantic,
        ollama=OllamaExecutor(
            base_url="http://test", default_model="llama3.2:3b", tier="L3"
        ),
        ollama_l4=OllamaExecutor(
            base_url="http://test", default_model="llama3.1:8b", tier="L4"
        ),
        ollama_l5=OllamaExecutor(
            base_url="http://test", default_model="qwen2.5:14b", tier="L5"
        ),
        metrics=metrics,
        frontier_enabled=False,
        ttft_aware=True,
        ttft_percentile=0.95,
        ttft_min_samples=20,
    )
    # ~300 words → heuristic L4; seeded TTFT prefers L3.
    req = InternalRequest(
        messages=[Message(role="user", content=" ".join(["word"] * 300))],
        model="daari",
    )

    def one() -> str:
        return router._choose_initial_tier(req)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=TTFT_PREFERENCE_CONCURRENCY) as pool:
        futures = [
            pool.submit(one) for _ in range(TTFT_PREFERENCE_CONCURRENCY)
        ]
        tiers = [f.result() for f in as_completed(futures)]
    elapsed = time.perf_counter() - start

    assert tiers == ["L3"] * TTFT_PREFERENCE_CONCURRENCY
    text_out = render_prometheus(metrics)
    assert 'daari_ttft_preference_total{from="L4",to="L3"}' in text_out
    # Extract the counter value after the labels.
    line = next(
        ln
        for ln in text_out.splitlines()
        if ln.startswith('daari_ttft_preference_total{from="L4",to="L3"}')
    )
    count = float(line.rsplit(" ", 1)[-1])
    assert count >= TTFT_PREFERENCE_CONCURRENCY
    assert elapsed < TTFT_PREFERENCE_BURST_CEILING_S, (
        f"TTFT preference burst {elapsed:.4f}s exceeds ceiling "
        f"{TTFT_PREFERENCE_BURST_CEILING_S}s (preference-path regression)"
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_hard_rate_limit_reject_burst_under_ceiling(settings, monkeypatch):
    """N concurrent over-RPM requests → all 429; rejects_total ≥ N under a wall (#585)."""
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    # Disable soft band so the prefilled window hard-rejects immediately.
    settings.frontier.soft_budget_ratio = 0.0
    settings.observability.prometheus = True

    limiter = RateLimiter(MemoryCounterBackend(), default_rpm=HARD_REJECT_RPM)
    for _ in range(HARD_REJECT_RPM):
        decision = limiter.check(key_id="master", model="daari", tokens=8)
        assert decision.allowed

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.rate_limiter = limiter

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        raise AssertionError("upstream must not run after hard rate-limit reject")

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    chat = {"model": "daari", "messages": [{"role": "user", "content": "hard-burst"}]}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def one():
            return await client.post(
                "/v1/chat/completions",
                json=chat,
                headers={"X-Daari-No-Cache": "true"},
            )

        start = time.perf_counter()
        responses = await asyncio.gather(
            *[one() for _ in range(HARD_REJECT_CONCURRENCY)]
        )
        elapsed = time.perf_counter() - start

        metrics = await client.get("/metrics")

    assert all(r.status_code == 429 for r in responses), [
        r.status_code for r in responses
    ]
    text_out = metrics.text
    assert 'daari_rejects_total{kind="rate_limit"}' in text_out
    line = next(
        ln
        for ln in text_out.splitlines()
        if ln.startswith('daari_rejects_total{kind="rate_limit"}')
    )
    count = float(line.rsplit(" ", 1)[-1])
    assert count >= HARD_REJECT_CONCURRENCY
    assert elapsed < HARD_REJECT_BURST_CEILING_S, (
        f"hard reject burst {elapsed:.4f}s exceeds ceiling "
        f"{HARD_REJECT_BURST_CEILING_S}s (reject-path middleware regression)"
    )


def _record_frontier_spend(ledger, client_id: str, *, usd: float) -> None:
    """Record frontier usage at the flat fallback rate ($0.002 / 1k tokens)."""
    ledger.record(
        tier="L6",
        client_id=client_id,
        model="",
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
    )


def _record_requests(ledger, client_id: str, n: int) -> None:
    for _ in range(n):
        ledger.record(tier="L3", client_id=client_id, cache_hit=False)


def _app_with_virtual_key(settings, tmp_path):
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.observability.usage import UsageLedger

    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.observability.prometheus = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_hard_budget_402_burst_under_ceiling(settings, tmp_path):
    """N concurrent over-budget requests → all 402; rejects_total ≥ N under a wall (#592)."""
    from httpx import ASGITransport, AsyncClient

    app, store, ledger = _app_with_virtual_key(settings, tmp_path)
    key = store.create("budget-burst", client_id="key-budget", daily_budget_usd=1.0)
    _record_frontier_spend(ledger, "key-budget", usd=1.0)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        raise AssertionError("upstream must not run after hard budget 402")

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    chat = {"model": "daari", "messages": [{"role": "user", "content": "budget-burst"}]}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def one():
            return await client.post(
                "/v1/chat/completions",
                json=chat,
                headers={
                    "Authorization": f"Bearer {key.plaintext}",
                    "X-Daari-No-Cache": "true",
                },
            )

        start = time.perf_counter()
        responses = await asyncio.gather(
            *[one() for _ in range(HARD_402_CONCURRENCY)]
        )
        elapsed = time.perf_counter() - start

        metrics = await client.get(
            "/metrics", headers={"Authorization": "Bearer master"}
        )

    assert all(r.status_code == 402 for r in responses), [
        r.status_code for r in responses
    ]
    text_out = metrics.text
    assert 'daari_rejects_total{kind="budget"}' in text_out
    line = next(
        ln
        for ln in text_out.splitlines()
        if ln.startswith('daari_rejects_total{kind="budget"}')
    )
    count = float(line.rsplit(" ", 1)[-1])
    assert count >= HARD_402_CONCURRENCY
    assert elapsed < HARD_402_BURST_CEILING_S, (
        f"hard budget 402 burst {elapsed:.4f}s exceeds ceiling "
        f"{HARD_402_BURST_CEILING_S}s (402 reject-path middleware regression)"
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_hard_request_quota_402_burst_under_ceiling(settings, tmp_path):
    """N concurrent over-quota requests → all 402; rejects_total ≥ N under a wall (#592)."""
    from httpx import ASGITransport, AsyncClient

    app, store, ledger = _app_with_virtual_key(settings, tmp_path)
    key = store.create(
        "quota-burst",
        client_id="key-quota",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=1)],
    )
    _record_requests(ledger, "key-quota", 1)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        raise AssertionError("upstream must not run after hard request-quota 402")

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    chat = {"model": "daari", "messages": [{"role": "user", "content": "quota-burst"}]}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def one():
            return await client.post(
                "/v1/chat/completions",
                json=chat,
                headers={
                    "Authorization": f"Bearer {key.plaintext}",
                    "X-Daari-No-Cache": "true",
                },
            )

        start = time.perf_counter()
        responses = await asyncio.gather(
            *[one() for _ in range(HARD_402_CONCURRENCY)]
        )
        elapsed = time.perf_counter() - start

        metrics = await client.get(
            "/metrics", headers={"Authorization": "Bearer master"}
        )

    assert all(r.status_code == 402 for r in responses), [
        r.status_code for r in responses
    ]
    text_out = metrics.text
    assert 'daari_rejects_total{kind="request_quota"}' in text_out
    line = next(
        ln
        for ln in text_out.splitlines()
        if ln.startswith('daari_rejects_total{kind="request_quota"}')
    )
    count = float(line.rsplit(" ", 1)[-1])
    assert count >= HARD_402_CONCURRENCY
    assert elapsed < HARD_402_BURST_CEILING_S, (
        f"hard request-quota 402 burst {elapsed:.4f}s exceeds ceiling "
        f"{HARD_402_BURST_CEILING_S}s (402 reject-path middleware regression)"
    )


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_soft_request_quota_warn_burst_under_ceiling(settings, tmp_path):
    """N concurrent soft-band quota requests → 200 + soft header; soft_warnings ≥ N (#620)."""
    from httpx import ASGITransport, AsyncClient

    from daari.gateway.budget_headers import QUOTA_REQUESTS_WARNING_HEADER

    settings.frontier.soft_budget_ratio = 0.8
    app, store, ledger = _app_with_virtual_key(settings, tmp_path)
    key = store.create(
        "soft-quota-burst",
        client_id="key-soft-quota",
        budget_windows=[
            BudgetWindow("day", 0.0, max_requests=SOFT_REQUEST_QUOTA_CAP)
        ],
    )
    _record_requests(ledger, "key-soft-quota", SOFT_REQUEST_QUOTA_PREFILL)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=(
                "A confident soft-quota body with plenty of length to avoid escalation."
            ),
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    chat = {
        "model": "daari",
        "messages": [{"role": "user", "content": "soft-quota-burst"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def one():
            return await client.post(
                "/v1/chat/completions",
                json=chat,
                headers={
                    "Authorization": f"Bearer {key.plaintext}",
                    "X-Daari-No-Cache": "true",
                },
            )

        start = time.perf_counter()
        responses = await asyncio.gather(
            *[one() for _ in range(SOFT_REQUEST_QUOTA_CONCURRENCY)]
        )
        elapsed = time.perf_counter() - start

        metrics = await client.get(
            "/metrics", headers={"Authorization": "Bearer master"}
        )

    assert all(r.status_code == 200 for r in responses), [
        r.status_code for r in responses
    ]
    assert all(
        r.headers.get(QUOTA_REQUESTS_WARNING_HEADER) == "soft" for r in responses
    )
    text_out = metrics.text
    assert 'daari_soft_warnings_total{kind="request_quota"}' in text_out
    line = next(
        ln
        for ln in text_out.splitlines()
        if ln.startswith('daari_soft_warnings_total{kind="request_quota"}')
    )
    count = float(line.rsplit(" ", 1)[-1])
    assert count >= SOFT_REQUEST_QUOTA_CONCURRENCY
    assert elapsed < SOFT_REQUEST_QUOTA_BURST_CEILING_S, (
        f"soft request-quota warn burst {elapsed:.4f}s exceeds ceiling "
        f"{SOFT_REQUEST_QUOTA_BURST_CEILING_S}s "
        f"(soft-quota warn middleware regression)"
    )
