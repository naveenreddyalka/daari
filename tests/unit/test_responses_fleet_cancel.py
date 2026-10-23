"""Fleet-shared Responses background cancel across replicas (#1874)."""

from __future__ import annotations

import asyncio

import pytest

from daari.gateway import responses_job_cancel as cancel_mod


class FakeSharedStore:
    """Hermetic stand-in for Redis cancel keys shared by two 'pods'."""

    def __init__(self) -> None:
        self.flags: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.flags.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.flags[key] = value
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.flags:
                del self.flags[key]
                n += 1
        return n


@pytest.fixture(autouse=True)
def _reset_cancel_coord():
    cancel_mod.reset_job_cancel_coordinator()
    yield
    cancel_mod.reset_job_cancel_coordinator()


@pytest.mark.asyncio
async def test_pod_b_cancel_stops_pod_a_background_task():
    """Pod A owns the task; Pod B cancel via shared store stops it (#1874)."""
    shared = FakeSharedStore()
    cancel_mod.set_job_cancel_backend(shared)

    started = asyncio.Event()
    finished = asyncio.Event()
    ran_to_completion = False

    async def slow_job() -> None:
        nonlocal ran_to_completion
        started.set()
        try:
            await asyncio.sleep(5.0)
            ran_to_completion = True
        except asyncio.CancelledError:
            raise
        finally:
            finished.set()

    rid = "resp_fleet_cancel_1"
    # Pod A: register local task + start cooperative watcher.
    task = asyncio.create_task(slow_job())
    cancel_mod.register_local_job(rid, task)
    cancel_mod.ensure_cancel_watcher()

    await asyncio.wait_for(started.wait(), timeout=1.0)

    # Pod B: no local task — only the shared Redis flag (same store as A).
    assert rid in cancel_mod._LOCAL_JOBS  # still owned by "pod A"
    shared.set(f"daari:responses:bg_cancel:{rid}", "1")

    await asyncio.wait_for(finished.wait(), timeout=2.0)
    assert task.done()
    assert ran_to_completion is False
    assert cancel_mod.is_cancel_requested(rid) is True


def test_local_signal_cancel_without_shared_backend():
    """Single-process: signal_cancel still marks + stops a local task."""
    assert cancel_mod.job_cancel_backend_name() == "local"
    rid = "resp_local_only"
    cancel_mod.signal_cancel(rid)
    assert cancel_mod.is_cancel_requested(rid) is True


def test_configure_uses_redis_when_cache_backend_redis():
    from types import SimpleNamespace

    fake = FakeSharedStore()

    def _connect(url: str, *, timeout_seconds: float = 2.0) -> FakeSharedStore:
        assert "redis://" in url
        return fake

    settings = SimpleNamespace(
        cache=SimpleNamespace(
            backend="redis",
            redis_url="redis://localhost:6379/0",
            redis_timeout_seconds=1.5,
        )
    )
    cancel_mod.configure_job_cancel_store(settings, connect_redis=_connect)
    assert cancel_mod.job_cancel_backend_name() == "redis"
    cancel_mod.signal_cancel("resp_x")
    assert fake.get("daari:responses:bg_cancel:resp_x") == "1"


def test_configure_stays_local_when_cache_not_redis():
    from types import SimpleNamespace

    settings = SimpleNamespace(cache=SimpleNamespace(backend="disk", redis_url=""))
    cancel_mod.configure_job_cancel_store(settings)
    assert cancel_mod.job_cancel_backend_name() == "local"
