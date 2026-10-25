"""Signed completion webhooks for background Responses jobs (#1892, #1913)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import AlertSettings, Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.response_store import ResponseStore
from daari.gateway.responses import ResponsesGatewayAdapter
from daari.observability.budget_alerts import (
    TIMESTAMP_HEADER,
    SIGNATURE_HEADER,
    verify_webhook_signature,
)
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.observability.responses_webhooks import (
    deliver_responses_completion_webhook,
    responses_completion_payload,
    schedule_responses_completion_webhook,
    wait_responses_webhooks,
)
from daari.observability.webhook_secrets import rotate_webhook_secret_in_config
from daari.setup.doctor import _check_webhook_secret_previous_stale


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


def test_alert_settings_default_responses_completion_webhook_off():
    alerts = AlertSettings()
    assert alerts.responses_completion_webhook_url == ""
    assert alerts.responses_completion_webhook_secret == ""
    assert alerts.responses_completion_webhook_secret_previous == ""
    assert alerts.responses_completion_webhook_secret_rotated_at == ""


def test_payload_includes_id_status_model_usage():
    body = {
        "id": "resp_abc",
        "status": "completed",
        "model": "gpt-4.1",
        "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
    }
    payload = responses_completion_payload(body)
    assert payload == {
        "id": "resp_abc",
        "status": "completed",
        "model": "gpt-4.1",
        "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
    }


def test_deliver_noop_when_url_unset(monkeypatch):
    called = []

    class BoomTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            called.append(request)
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="",
        secret="sec",
        body={"id": "resp_1", "status": "completed", "model": "m"},
        transport=BoomTransport(),
    )
    assert called == []


def test_deliver_signs_and_posts_completed(monkeypatch):
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    body = {
        "id": "resp_ok",
        "status": "completed",
        "model": "gpt-4.1",
        "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    }
    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_test",
        body=body,
        transport=Capture(),
    )
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://hooks.example/responses"
    raw = req.content
    ts = req.headers[TIMESTAMP_HEADER]
    sig = req.headers[SIGNATURE_HEADER]
    assert verify_webhook_signature(raw, sig, "whsec_test", ts)
    assert json.loads(raw)["status"] == "completed"
    assert json.loads(raw)["id"] == "resp_ok"


def test_deliver_signs_and_posts_failed():
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_test",
        body={"id": "resp_fail", "status": "failed", "model": "m", "error": {"code": "x"}},
        transport=Capture(),
    )
    assert len(seen) == 1
    assert json.loads(seen[0].content)["status"] == "failed"


def test_deliver_failure_logs_does_not_raise():
    class FailTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="nope")

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_test",
        body={"id": "resp_x", "status": "completed", "model": "m"},
        transport=FailTransport(),
    )


@pytest.mark.asyncio
async def test_background_completed_dispatches_webhook(monkeypatch, tmp_path):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append({"url": url, "secret": secret, "body": body})

    monkeypatch.setattr(
        "daari.gateway.responses.schedule_responses_completion_webhook",
        fake_schedule,
    )

    class Ctx:
        settings = Settings()
        settings.alerts.responses_completion_webhook_url = "https://hooks.example/r"
        settings.alerts.responses_completion_webhook_secret = "sec"

        class router:
            @staticmethod
            async def route(internal):
                return InternalResponse(
                    content="done",
                    model="local",
                    daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
                )

    store = ResponseStore(tmp_path / "responses.sqlite3")
    store.put(
        "resp_bg",
        {"id": "resp_bg", "object": "response", "status": "queued", "output": []},
        conversation=[],
        stored=True,
    )
    internal = InternalRequest(messages=[Message(role="user", content="hi")], model="daari")
    await ResponsesGatewayAdapter._run_background(
        Ctx(),  # type: ignore[arg-type]
        internal,
        "resp_bg",
        2,
        False,
        None,
        [Message(role="user", content="hi")],
        store,
    )
    assert len(seen) == 1
    assert seen[0]["url"] == "https://hooks.example/r"
    assert seen[0]["body"]["status"] == "completed"
    assert seen[0]["body"]["id"] == "resp_bg"


@pytest.mark.asyncio
async def test_background_failed_dispatches_webhook(monkeypatch, tmp_path):
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.responses.schedule_responses_completion_webhook",
        fake_schedule,
    )

    class Ctx:
        settings = Settings()
        settings.alerts.responses_completion_webhook_url = "https://hooks.example/r"
        settings.alerts.responses_completion_webhook_secret = "sec"

        class router:
            @staticmethod
            async def route(internal):
                raise RuntimeError("boom")

    store = ResponseStore(tmp_path / "responses.sqlite3")
    store.put(
        "resp_bad",
        {"id": "resp_bad", "object": "response", "status": "queued", "output": []},
        conversation=[],
        stored=True,
    )
    internal = InternalRequest(messages=[Message(role="user", content="hi")], model="daari")
    await ResponsesGatewayAdapter._run_background(
        Ctx(),  # type: ignore[arg-type]
        internal,
        "resp_bad",
        2,
        False,
        None,
        [],
        store,
    )
    assert len(seen) == 1
    assert seen[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_background_disabled_skips_deliver(monkeypatch, tmp_path):
    seen: list[dict] = []

    def fake_schedule(**kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(
        "daari.gateway.responses.schedule_responses_completion_webhook",
        fake_schedule,
    )

    class Ctx:
        settings = Settings()  # URL empty

        class router:
            @staticmethod
            async def route(internal):
                return InternalResponse(
                    content="done",
                    model="local",
                    daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
                )

    store = ResponseStore(tmp_path / "responses.sqlite3")
    store.put(
        "resp_off",
        {"id": "resp_off", "object": "response", "status": "queued", "output": []},
        conversation=[],
        stored=True,
    )
    await ResponsesGatewayAdapter._run_background(
        Ctx(),  # type: ignore[arg-type]
        InternalRequest(messages=[Message(role="user", content="hi")], model="daari"),
        "resp_off",
        2,
        False,
        None,
        [],
        store,
    )
    # Helper still invoked so soft-fail lives in one place; URL empty → no HTTP.
    assert len(seen) == 1
    assert seen[0]["url"] == ""


def test_deliver_retries_once_on_5xx():
    attempts: list[int] = []

    class Flaky(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(503, text="busy")
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_test",
        body={"id": "resp_r", "status": "completed", "model": "m"},
        transport=Flaky(),
        retry_backoff_seconds=0.0,
    )
    assert len(attempts) == 2


def test_deliver_retries_once_on_transport_error():
    attempts: list[int] = []

    class Flaky(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ConnectError("down")
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_test",
        body={"id": "resp_t", "status": "completed", "model": "m"},
        transport=Flaky(),
        retry_backoff_seconds=0.0,
    )
    assert len(attempts) == 2


def test_deliver_records_prometheus_result():
    metrics = Metrics()

    class Ok(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="sec",
        body={"id": "resp_m", "status": "completed", "model": "m"},
        transport=Ok(),
        metrics=metrics,
    )
    assert metrics.responses_webhooks.get("ok") == 1
    text = render_prometheus(metrics)
    assert 'daari_responses_webhooks_total{result="ok"}' in text


def test_deliver_signs_with_previous_secret():
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    deliver_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="whsec_new",
        previous_secret="whsec_old",
        body={"id": "resp_rot", "status": "completed", "model": "m"},
        transport=Capture(),
    )
    assert len(seen) == 1
    sig = seen[0].headers[SIGNATURE_HEADER]
    assert "," in sig


def test_fleet_claim_cancel_and_complete_deliver_once():
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
        schedule_responses_completion_webhook(
            url="https://hooks.example/responses",
            secret="sec",
            body={"id": "resp_race", "status": status, "model": "m"},
            transport=transport,
            redis=shared,
        )

    a = threading.Thread(target=fire, args=("cancelled",))
    b = threading.Thread(target=fire, args=("completed",))
    a.start()
    b.start()
    a.join(timeout=5)
    b.join(timeout=5)
    wait_responses_webhooks()
    assert len(hits) == 1
    assert len(shared.calls) == 2
    assert all(call["nx"] is True for call in shared.calls)
    assert "resp_race" in shared.calls[0]["name"]


@pytest.mark.asyncio
async def test_slow_webhook_does_not_block_event_loop():
    started = threading.Event()

    class Slow(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            started.set()
            time.sleep(1.5)
            return httpx.Response(200)

    schedule_responses_completion_webhook(
        url="https://hooks.example/responses",
        secret="sec",
        body={"id": "resp_slow", "status": "completed", "model": "m"},
        transport=Slow(),
    )
    assert started.wait(timeout=2.0)
    t0 = time.monotonic()
    await asyncio.sleep(0.05)
    assert time.monotonic() - t0 < 0.5
    wait_responses_webhooks(timeout=5.0)


def test_rotate_responses_family(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  responses_completion_webhook_secret: old-secret\n",
        encoding="utf-8",
    )
    moment = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    result = rotate_webhook_secret_in_config(
        path, family="responses", new_secret="new-secret", now=moment
    )
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["responses_completion_webhook_secret"] == "new-secret"
    assert loaded["alerts"]["responses_completion_webhook_secret_previous"] == "old-secret"
    assert (
        loaded["alerts"]["responses_completion_webhook_secret_rotated_at"]
        == moment.isoformat()
    )
    assert result["had_previous"] is True


def test_cli_rotate_secret_responses(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  responses_completion_webhook_secret: old\n",
        encoding="utf-8",
    )
    settings = Settings()
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"})
    result = runner.invoke(
        cli_app,
        ["alerts", "rotate-secret", "responses", "--secret", "new", "--config", str(path)],
    )
    assert result.exit_code == 0, result.output
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["responses_completion_webhook_secret"] == "new"
    assert loaded["alerts"]["responses_completion_webhook_secret_previous"] == "old"


def test_doctor_tips_stale_responses_previous(settings: Settings):
    settings.alerts.responses_completion_webhook_secret_previous = "old"
    settings.alerts.responses_completion_webhook_secret_rotated_at = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    tip = _check_webhook_secret_previous_stale(settings)
    assert tip is not None
    assert "responses" in tip.detail
