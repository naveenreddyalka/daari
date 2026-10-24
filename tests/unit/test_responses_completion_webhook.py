"""Signed completion webhooks for background Responses jobs (#1892)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import AlertSettings, Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.response_store import ResponseStore
from daari.gateway.responses import ResponsesGatewayAdapter
from daari.observability.budget_alerts import (
    TIMESTAMP_HEADER,
    SIGNATURE_HEADER,
    verify_webhook_signature,
)
from daari.observability.responses_webhooks import (
    deliver_responses_completion_webhook,
    responses_completion_payload,
)


def test_alert_settings_default_responses_completion_webhook_off():
    alerts = AlertSettings()
    assert alerts.responses_completion_webhook_url == ""
    assert alerts.responses_completion_webhook_secret == ""


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

    def fake_deliver(*, url, secret, body, transport=None):
        seen.append({"url": url, "secret": secret, "body": body})

    monkeypatch.setattr(
        "daari.gateway.responses.deliver_responses_completion_webhook",
        fake_deliver,
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

    def fake_deliver(*, url, secret, body, transport=None):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.responses.deliver_responses_completion_webhook",
        fake_deliver,
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

    def fake_deliver(**kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(
        "daari.gateway.responses.deliver_responses_completion_webhook",
        fake_deliver,
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
