"""Signed completion webhooks for /v1/batches jobs (#2069)."""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

from daari.config.settings import AlertSettings, Settings
from daari.gateway.batches import (
    STATUS_CANCELLED,
    STATUS_CANCELLING,
    STATUS_COMPLETED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_VALIDATING,
    BatchStore,
)
from daari.observability.batch_webhooks import (
    batch_completion_payload,
    deliver_batch_completion_webhook,
    schedule_batch_completion_webhook,
    wait_batch_webhooks,
)
from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_webhook_signature,
)
from daari.security.offline_mode import configure_offline_mode


class FakeRedis:
    """In-memory SET NX EX stand-in for fleet webhook claims."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None):
        with self._lock:
            self.calls.append({"name": name, "value": value, "nx": nx, "ex": ex})
            if nx and name in self.store:
                return None
            self.store[name] = value
            return True


@pytest.fixture(autouse=True)
def _reset_offline_mode():
    configure_offline_mode(enabled=False, allow_hosts=())
    yield
    configure_offline_mode(enabled=False, allow_hosts=())


def test_alert_settings_default_batch_completion_webhook_off():
    alerts = AlertSettings()
    assert alerts.batches_completion_webhook_url == ""
    assert alerts.batches_completion_webhook_secret == ""
    assert alerts.batches_completion_webhook_secret_previous == ""
    assert alerts.batches_completion_webhook_secret_rotated_at == ""


def test_payload_includes_id_status_request_counts():
    body = {
        "id": "batch_abc",
        "status": "completed",
        "request_counts": {"total": 3, "completed": 2, "failed": 1},
        "endpoint": "/v1/chat/completions",
    }
    payload = batch_completion_payload(body)
    assert payload == {
        "id": "batch_abc",
        "status": "completed",
        "request_counts": {"total": 3, "completed": 2, "failed": 1},
    }


def test_deliver_noop_when_url_unset():
    called: list[httpx.Request] = []

    class BoomTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            called.append(request)
            return httpx.Response(200)

    result = deliver_batch_completion_webhook(
        url="",
        secret="sec",
        body={"id": "batch_1", "status": "completed", "request_counts": {"total": 1}},
        transport=BoomTransport(),
    )
    assert result == "skipped"
    assert called == []


def test_deliver_signs_and_posts_completed():
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    body = {
        "id": "batch_ok",
        "status": "completed",
        "request_counts": {"total": 2, "completed": 2, "failed": 0},
    }
    deliver_batch_completion_webhook(
        url="https://hooks.example/batches",
        secret="whsec_test",
        body=body,
        transport=Capture(),
    )
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://hooks.example/batches"
    raw = req.content
    ts = req.headers[TIMESTAMP_HEADER]
    sig = req.headers[SIGNATURE_HEADER]
    assert verify_webhook_signature(raw, sig, "whsec_test", ts)
    parsed = json.loads(raw)
    assert parsed["status"] == "completed"
    assert parsed["id"] == "batch_ok"
    assert parsed["request_counts"]["total"] == 2


def test_deliver_offline_mode_refuses_offbox(monkeypatch):
    called: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            called.append(request)
            return httpx.Response(200)

    configure_offline_mode(enabled=True)
    monkeypatch.setattr(
        "daari.security.offline_mode._default_resolve",
        lambda _h: ["93.184.216.34"],
    )
    result = deliver_batch_completion_webhook(
        url="https://hooks.example/batches",
        secret="sec",
        body={"id": "batch_off", "status": "completed", "request_counts": {"total": 0}},
        transport=Capture(),
    )
    assert result == "error"
    assert called == []


@pytest.mark.asyncio
async def test_terminal_completed_fires_webhook(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append({"url": url, "secret": secret, "body": body})

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore()
    store.completion_webhook_url = "https://hooks.example/b"
    store.completion_webhook_secret = "sec"
    job = store.create(
        endpoint="/v1/chat/completions",
        requests=[
            {
                "custom_id": "r1",
                "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            }
        ],
    )
    assert job.status == STATUS_VALIDATING

    async def execute_one(_body: dict) -> dict:
        return {"id": "chatcmpl_1", "choices": []}

    await store.run_job(job.id, execute_one)
    assert store.get(job.id).status == STATUS_COMPLETED
    assert len(seen) == 1
    assert seen[0]["url"] == "https://hooks.example/b"
    assert seen[0]["body"]["status"] == STATUS_COMPLETED
    assert seen[0]["body"]["id"] == job.id
    assert seen[0]["body"]["request_counts"]["total"] == 1


@pytest.mark.asyncio
async def test_terminal_cancelled_fires_webhook(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore()
    store.completion_webhook_url = "https://hooks.example/b"
    job = store.create(
        endpoint="/v1/chat/completions",
        requests=[
            {
                "custom_id": "r1",
                "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            }
        ],
    )
    cancelled = store.cancel(job.id)
    assert cancelled is not None
    assert cancelled.status == STATUS_CANCELLED
    assert len(seen) == 1
    assert seen[0]["status"] == STATUS_CANCELLED


@pytest.mark.asyncio
async def test_non_terminal_transitions_do_not_fire(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(**kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore()
    store.completion_webhook_url = "https://hooks.example/b"
    job = store.create(
        endpoint="/v1/chat/completions",
        requests=[
            {
                "custom_id": "r1",
                "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            }
        ],
    )
    assert job.status == STATUS_VALIDATING
    assert seen == []

    # Mid-flight cancel while a worker would be running → cancelling (not terminal).
    store._running.add(job.id)
    job.status = STATUS_IN_PROGRESS
    cancelling = store.cancel(job.id)
    assert cancelling is not None
    assert cancelling.status == STATUS_CANCELLING
    assert seen == []


def test_create_validation_failed_fires_webhook(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore()
    store.completion_webhook_url = "https://hooks.example/b"
    job = store.create(input_file_id="file-missing", endpoint="/v1/chat/completions")
    assert job.status == STATUS_FAILED
    assert len(seen) == 1
    assert seen[0]["status"] == STATUS_FAILED


@pytest.mark.asyncio
async def test_expired_fires_webhook(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore(yield_to_interactive=False)
    store.completion_webhook_url = "https://hooks.example/b"
    job = store.create(
        endpoint="/v1/chat/completions",
        requests=[
            {
                "custom_id": "r1",
                "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]},
            }
        ],
    )
    job.expires_at = int(time.time()) - 10
    store._persist(job)

    async def execute_one(_body: dict) -> dict:
        return {"id": "x"}

    await store.run_job(job.id, execute_one)
    assert store.get(job.id).status == STATUS_EXPIRED
    assert len(seen) == 1
    assert seen[0]["status"] == STATUS_EXPIRED


def test_per_request_callback_url_overrides_settings(monkeypatch):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append({"url": url, "body": body})

    monkeypatch.setattr(
        "daari.gateway.batches.schedule_batch_completion_webhook",
        fake_schedule,
    )

    store = BatchStore()
    store.completion_webhook_url = "https://hooks.example/settings"
    job = store.create(
        input_file_id="file-missing",
        endpoint="/v1/chat/completions",
        callback_url="https://hooks.example/per-job",
    )
    assert job.status == STATUS_FAILED
    assert job.callback_url == "https://hooks.example/per-job"
    assert len(seen) == 1
    assert seen[0]["url"] == "https://hooks.example/per-job"


def test_fleet_claim_dedupes_once():
    shared = FakeRedis()
    hits: list[httpx.Request] = []
    barrier = threading.Barrier(2)

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            hits.append(request)
            return httpx.Response(200)

    transport = Capture()

    def fire(status: str) -> None:
        barrier.wait(timeout=2)
        schedule_batch_completion_webhook(
            url="https://hooks.example/batches",
            secret="sec",
            body={
                "id": "batch_race",
                "status": status,
                "request_counts": {"total": 1, "completed": 0, "failed": 0},
            },
            transport=transport,
            redis=shared,
        )

    a = threading.Thread(target=fire, args=("cancelled",))
    b = threading.Thread(target=fire, args=("completed",))
    a.start()
    b.start()
    a.join(timeout=5)
    b.join(timeout=5)
    wait_batch_webhooks()
    assert len(hits) == 1
    assert len(shared.calls) == 2
    assert all(call["nx"] is True for call in shared.calls)
    assert "batch_race" in shared.calls[0]["name"]


def test_apply_settings_wires_store():
    from daari.observability.batch_webhooks import apply_batch_webhook_settings

    settings = Settings()
    settings.alerts.batches_completion_webhook_url = "https://hooks.example/b"
    settings.alerts.batches_completion_webhook_secret = "sec"
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://localhost:6379/0"
    store = BatchStore()
    apply_batch_webhook_settings(store, settings)
    assert store.completion_webhook_url == "https://hooks.example/b"
    assert store.completion_webhook_secret == "sec"
    assert store.completion_webhook_redis_url == "redis://localhost:6379/0"
