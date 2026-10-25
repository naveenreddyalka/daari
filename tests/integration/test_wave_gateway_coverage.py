"""Hermetic gateway coverage for the 2026-10-24/25 wave (#1930).

Covers streamed TTS spend, Responses completion webhooks, org enforcement
ingest, Decisions input_json+image L0, Anthropic stream cache writes,
user_rpd isolation, and fleet-shared breakers. Same convention as other
non-@integration modules under tests/integration/.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import AnthropicSettings
from daari.enterprise.anthropic_org_webhooks import (
    ENFORCEMENT_OPENED,
    sign_standard_webhook,
)
from daari.enterprise.enforcement_sync import EnforcementStore
from daari.gateway import speech, systemone
from daari.gateway.cost_headers import COST_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    verify_webhook_signature,
)
from daari.observability.responses_webhooks import wait_responses_webhooks
from daari.router import breaker_redis
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

SECRET_RAW = b"test-org-webhook-secret-key!!"
ORG_SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode()
FROZEN = 1_700_000_030.0
CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


def _freeze(monkeypatch, clock: dict[str, float]) -> None:
    monkeypatch.setattr(time, "time", lambda: clock["now"])
    monkeypatch.setattr("daari.auth.rate_limit.time.time", lambda: clock["now"])


def _org_event(event_type: str, *, profile_id: str) -> dict:
    return {
        "type": "event",
        "id": "whe_wave_coverage_1",
        "created_at": "2026-10-15T17:02:41Z",
        "data": {
            "type": event_type,
            "id": profile_id,
            "enforcement_action_id": "enac_wave_1",
            "organization_id": "org_wave_1",
        },
    }


def _signed_org_headers(body: bytes, secret: str = ORG_SECRET) -> dict[str, str]:
    msg_id = "msg_wave_org_1"
    timestamp = str(int(time.time()))
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": sign_standard_webhook(body, secret, msg_id, timestamp),
        "content-type": "application/json",
    }


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def incr(self, key: str) -> int:
        cur = int(self.store.get(key) or 0) + 1
        self.store[key] = str(cur)
        return cur

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = int(seconds)
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                n += 1
            self.ttls.pop(key, None)
        return n

    def keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]


@pytest.fixture(autouse=True)
def _clean_shared_breakers():
    breaker_redis.set_breaker_redis(None)
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)
    yield
    breaker_redis.set_breaker_redis(None)
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)


# --- (a) streamed TTS + spend ---


@pytest.mark.asyncio
async def test_streamed_speech_records_spend_row(settings, tmp_path, monkeypatch):
    """Chunked /v1/audio/speech finalizes a tts spend row (#1930)."""

    class _FakeUpstream:
        status_code = 200
        headers = httpx.Headers(
            {"content-type": "audio/mpeg", "transfer-encoding": "chunked"}
        )

        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"FIRST"
            yield b"SECOND"

        async def aread(self):
            raise AssertionError("stream path must not buffer via aread")

    @asynccontextmanager
    async def _fake_stream(client, method, url, **kwargs):
        assert method == "POST"
        yield _FakeUpstream()

    monkeypatch.setattr(speech, "deadline_bounded_stream", _fake_stream)
    speech._http = httpx.AsyncClient()
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "ignored", "input": "stream charge", "voice": "alloy"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    assert response.content == b"FIRSTSECOND"
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "tts"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["model"] == "kokoro"
    await speech.aclose_http()


# --- (b) Responses completion webhook ---


@pytest.mark.asyncio
async def test_background_responses_delivers_signed_completion_webhook(
    settings, monkeypatch
):
    seen: list[httpx.Request] = []

    class Capture(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

    transport = Capture()
    real_deliver = __import__(
        "daari.observability.responses_webhooks", fromlist=["deliver_responses_completion_webhook"]
    ).deliver_responses_completion_webhook

    def deliver_with_capture(**kwargs):
        kwargs["transport"] = transport
        return real_deliver(**kwargs)

    monkeypatch.setattr(
        "daari.observability.responses_webhooks.deliver_responses_completion_webhook",
        deliver_with_capture,
    )

    settings.alerts.responses_completion_webhook_url = "https://hooks.example/responses"
    settings.alerts.responses_completion_webhook_secret = "whsec_test"
    app = _app(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="done in background",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=5),
        )

    app.state.ctx.router.route = fake_route

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "later", "background": True},
        )
        assert created.status_code == 200
        assert created.json()["status"] == "queued"
        response_id = created.json()["id"]
        body = None
        for _ in range(40):
            fetched = await client.get(f"/v1/responses/{response_id}")
            body = fetched.json()
            if body.get("status") == "completed":
                break
            await asyncio.sleep(0.05)
    assert body is not None and body["status"] == "completed"
    wait_responses_webhooks(timeout=5.0)
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://hooks.example/responses"
    raw = req.content
    ts = req.headers[TIMESTAMP_HEADER]
    sig = req.headers[SIGNATURE_HEADER]
    assert verify_webhook_signature(raw, sig, "whsec_test", ts)
    payload = json.loads(raw)
    assert payload["status"] == "completed"
    assert payload["id"] == response_id


# --- (c) org enforcement webhook ---


@pytest.mark.asyncio
async def test_org_enforcement_webhook_updates_readable_state(
    settings, tmp_path, monkeypatch
):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = False
    profile_id = "uprof_wave_coverage"
    settings.anthropic = AnthropicSettings(
        org_webhook_signing_secret=ORG_SECRET,
        enforcement_state_path=str(tmp_path / "enforcement.json"),
        user_profiles={"erin": profile_id},
    )
    app = _app(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/v1/user_profiles/{profile_id}")
        return httpx.Response(
            200,
            json={
                "type": "user_profile",
                "id": profile_id,
                "enforcement_status": "banned",
                "enforcement_actions": [
                    {
                        "type": "ban",
                        "id": "enac_wave_1",
                        "reason": "fraud_or_abuse",
                        "opened_at": "2026-10-15T17:02:41Z",
                        "expires_at": None,
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "daari.enterprise.anthropic_org_webhooks._default_transport",
        lambda: httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        type(settings),
        "resolve_frontier_api_key",
        lambda self: "sk-ant-test",
        raising=False,
    )

    body = json.dumps(_org_event(ENFORCEMENT_OPENED, profile_id=profile_id)).encode()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/webhooks/anthropic/org",
            content=body,
            headers=_signed_org_headers(body),
        )
    assert response.status_code == 200
    assert response.json()["enforcement_status"] == "banned"
    store = EnforcementStore(Path(settings.anthropic.enforcement_state_path))
    rows = store.load()
    assert len(rows) == 1
    assert rows[0]["profile_id"] == profile_id
    assert rows[0]["enforcement_status"] == "banned"
    assert rows[0]["end_users"] == ["erin"]


# --- (d) decisions input_json + image + L0 ---


@pytest.mark.asyncio
async def test_decisions_input_json_and_image_l0_fingerprint(settings, monkeypatch):
    from daari.gateway import systemone

    calls = {"n": 0}
    systemone_ok = {
        "model": "nimble",
        "answers": {
            "department": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.9, "other": 0.1},
                "confidence": 0.9,
            }
        },
        "usage": {"input_tokens": 40, "output_tokens": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        payload = json.loads(request.read())
        assert "49" in payload["state"] or "duplicate" in payload["state"].lower()
        assert payload.get("images") == ["aGVsbG8="]
        return httpx.Response(200, json=systemone_ok)

    systemone._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.systemone.httpx.AsyncClient", Patched)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    body = {
        "model": "nimble",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Inspect the charge."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,aGVsbG8=",
                    },
                ],
            }
        ],
        "input_json": {
            "ticket": {"body": "Please refund the duplicate charge."},
            "order": {"charges": [49, 49]},
        },
        "questions": [
            {
                "type": "choice",
                "name": "department",
                "instructions": "Which department?",
                "choices": [{"value": "billing"}, {"value": "other"}],
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/decisions", json=body)
        second = await client.post("/v1/decisions", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["daari_meta"]["tier"] == "decisions"
    assert second.status_code == 200
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert second.json()["daari_meta"]["cache_hit"] is True
    assert calls["n"] == 1


# --- (e) Anthropic streamed cache_creation → spend ---


def _anthropic_sse_with_cache_write(*, write_tokens: int) -> bytes:
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_wave",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-4-5",
                "content": [],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 700,
                    "cache_creation_input_tokens": write_tokens,
                },
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "cached"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 4},
        },
        {"type": "message_stop"},
    ]
    parts = []
    for event in events:
        parts.append(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n")
    return "".join(parts).encode()


async def _low_confidence(_request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="no",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
    )


async def _low_confidence_stream(_request: InternalRequest):
    yield {"message": {"content": "no"}, "done": True}


@pytest.mark.asyncio
async def test_anthropic_stream_cache_creation_hits_spend(
    settings, tmp_path, monkeypatch
):
    """Anthropic stream cache_creation_input_tokens lands on spend + cost header (#1930)."""
    write_tokens = 100
    _enable_spend(settings, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_anthropic_sse_with_cache_write(write_tokens=write_tokens),
            headers={"content-type": "text/event-stream"},
        )

    app = _app(settings)
    frontier = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-haiku-4-5",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    app.state.ctx.router.frontier = frontier
    app.state.ctx.router.frontier_enabled = True
    # Short local stream ("no") scores confidence 0 → frontier relay (#155).
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _low_confidence)
    seen: set[int] = set()
    for attr in ("ollama_l3", "ollama_l4", "ollama_l5", "ollama"):
        executor = getattr(app.state.ctx.router, attr, None)
        if executor is None or id(executor) in seen:
            continue
        seen.add(id(executor))
        monkeypatch.setattr(executor, "stream", _low_confidence_stream)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # OpenAI chat stream path relays Anthropic frontier SSE (same as #1766).
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-haiku-4-5",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert response.status_code == 200, response.text
    assert getattr(frontier, "last_stream_cache_write_tokens", None) == write_tokens
    assert COST_HEADER in response.headers
    rows = _spend_rows(app)
    assert rows
    assert rows[-1]["cache_write_tokens"] == write_tokens
    assert float(response.headers[COST_HEADER]) == pytest.approx(float(rows[-1]["cost_usd"]))


# --- (f) user_rpd isolates two users ---


@pytest.mark.asyncio
async def test_gateway_user_rpd_isolates_two_users(settings, tmp_path, monkeypatch):
    _freeze(monkeypatch, {"now": FROZEN})
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend())

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake
    created = store.create("shared", user_rpd=1)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alice_ok = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "alice"}, headers=headers
        )
        alice_denied = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "alice"}, headers=headers
        )
        bob_ok = await client.post(
            "/v1/chat/completions", json={**CHAT, "user": "bob"}, headers=headers
        )
    assert alice_ok.status_code == 200
    assert alice_denied.status_code == 429
    assert alice_denied.json()["error"]["type"] == "rate_limit_error"
    assert alice_denied.headers.get("x-ratelimit-scope") == "user"
    assert bob_ok.status_code == 200


# --- (g) fleet breaker shared across two app instances ---


@pytest.mark.asyncio
async def test_fleet_breaker_open_visible_on_second_app_instance(settings):
    """Trip on one app instance; a second instance sharing FakeRedis sees open (#1930)."""
    # create_app clears breaker Redis when cache.backend != redis — wire FakeRedis after.
    app_a = _app(settings)
    app_b = _app(settings)
    assert app_a.state.ctx is not None and app_b.state.ctx is not None

    redis = FakeRedis()
    breaker_redis.set_breaker_redis(redis)
    systemone.set_systemone_breaker_redis(redis)

    a = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    a.record_failure()
    assert a.state == "open"

    # Pod B: fresh local breaker, same Redis — must see open without local trip.
    b = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    assert b.state == "open"
    assert b.allow() is False

    # Systemone family: trip on "pod A", observe on wiped local dict ("pod B").
    base = "http://vllm.local:8000"
    breaker = systemone.breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    systemone._note_failure(base)
    systemone._breakers.clear()
    systemone._breaker_rejects.clear()
    rows = systemone.breaker_snapshot()
    assert rows and rows[0]["state"] == "open"
    with pytest.raises(systemone.SystemOneCircuitOpen):
        systemone._reject_if_open(base)
